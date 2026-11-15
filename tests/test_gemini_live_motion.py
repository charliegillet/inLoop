import unittest
import json
import os
from pathlib import Path
import tempfile

from scripts.live_gemini_motion import DirectionCheck, MotionWindow, make_raw_input, read_key, result_current


def state(generation='one'):
    samples=[dict(t=i*40,received_at=10+i*.04,ax=0.,ay=0.,az=1.,gx=0.,gy=0.,gz=0.) for i in range(30)]
    return dict(band=43,generation=generation,connected=True,enabled=True,published_at=11.2,
                sample=samples[-1],recent_samples=samples)


class WindowTests(unittest.TestCase):
    def test_fresh_contiguous_window_and_no_duplicate_samples(self):
        w=MotionWindow();s=state()
        self.assertTrue(w.ingest(s,11.2));self.assertIsNotNone(w.trial())
        count=len(w.samples);w.ingest(s,11.21)
        self.assertLessEqual(len(w.samples),count)  # The oldest point may age out.
        self.assertEqual(len({s['received_at'] for s in w.samples}),len(w.samples))

    def test_wrong_band_stale_and_disconnected_data_cannot_produce_window(self):
        for field,value in [('band',42),('connected',False),('enabled',False),('published_at',9.)]:
            with self.subTest(field=field):
                w=MotionWindow();w.ingest(state(),11.2)
                s=state();s[field]=value
                self.assertFalse(w.ingest(s,11.2));self.assertIsNone(w.trial())

    def test_reconnection_drops_previous_generation_samples(self):
        w=MotionWindow();w.ingest(state(),11.2)
        s=state('two');s['recent_samples']=s['recent_samples'][-2:]
        self.assertTrue(w.ingest(s,11.2));self.assertIsNone(w.trial())
        self.assertEqual(len(w.samples),2)

    def test_time_holes_are_not_compressed_into_gestures(self):
        w=MotionWindow();s=state();del s['recent_samples'][5:13]
        self.assertTrue(w.ingest(s,11.2));self.assertIsNone(w.trial())

    def test_invalid_numeric_samples_are_excluded(self):
        w=MotionWindow();s=state()
        for sample in s['recent_samples']:sample['gx']=float('nan')
        self.assertTrue(w.ingest(s,11.2));self.assertIsNone(w.trial())

    def test_raw_payload_preserves_every_sample_without_reference_or_derived_features(self):
        samples=state()['recent_samples']
        data=json.loads(make_raw_input(dict(samples=samples)))
        self.assertEqual(len(data['samples']),len(samples))
        for actual,expected in zip(data['samples'],samples):
            self.assertEqual(actual,[expected[k] for k in ('t','ax','ay','az','gx','gy','gz')])
        self.assertEqual(set(data),{'sensor','columns','samples'})
        self.assertNotIn('received_at',make_raw_input(dict(samples=samples)))

    def test_late_paused_replaced_or_disconnected_results_are_rejected(self):
        self.assertTrue(result_current('one',1,'one',1,12.,11.,True))
        for args in [('one',1,'two',1,12.,11.,True),('one',1,'one',2,12.,11.,True),
                     ('one',1,'one',1,14.,11.,True),('one',1,'one',1,12.,11.,False)]:
            self.assertFalse(result_current(*args))

    def test_sequential_windows_overlap_and_include_every_new_sample(self):
        w=MotionWindow();w.ingest(state(),11.2)
        first=w.trial();end=first['samples'][-1]['received_at']
        self.assertIsNone(w.trial(after=end))
        s=state()
        samples=[dict(s['sample'],t=i*40,received_at=10+i*.04) for i in range(5,55)]
        s.update(sample=samples[-1],recent_samples=samples,published_at=12.2)
        w.ingest(s,12.2);second=w.trial(after=end)
        self.assertIsNotNone(second)
        self.assertLessEqual(second['samples'][0]['received_at'],end)
        self.assertEqual([x['t'] for x in second['samples'] if x['received_at']>end],list(range(1200,2200,40)))

    def test_fresh_direction_check_rejects_stillness_and_interruption(self):
        c=DirectionCheck();c.begin();w=MotionWindow();w.ingest(state(),11.2)
        c.start(w,11.2,True);c.feed(w,14.,False)
        self.assertEqual(c.examples,{})
        self.assertIsNone(c.started)
        w.samples.clear()
        w.samples.extend(dict(state()['sample'],t=i*40,received_at=20+i*.04) for i in range(60))
        c.start(w,20.2,True);c.feed(w,22.5,True)
        self.assertEqual(c.examples,{})
        self.assertIn('No clear stroke',c.message)

    def test_four_new_strokes_enable_screen_examples_and_preserve_target(self):
        c=DirectionCheck();c.begin();w=MotionWindow();w.generation='live'
        for n in range(4):
            start=30+n*4
            samples=[dict(state()['sample'],t=(start+i*.04)*1000,received_at=start+i*.04,
                          ax=.4 if 10<=i<=20 else 0.) for i in range(60)]
            w.samples.clear();w.samples.extend(samples)
            c.start(w,start+.2,True);c.feed(w,start+2.5,True)
        self.assertFalse(c.active);self.assertEqual(set(c.examples),{'left','right','up','down'})
        payload=json.loads(make_raw_input(dict(samples=samples),c.examples))
        self.assertEqual(len(payload['samples']),len(samples))
        self.assertEqual(set(payload['screen_direction_examples']),set(c.examples))
        self.assertTrue(all(len(p)==12 for p in payload['screen_direction_examples'].values()))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'check.json'
            c.save(path,now=50)
            restored=DirectionCheck()
            self.assertTrue(restored.restore(path,now=60))
            self.assertFalse(restored.active)
            self.assertEqual(restored.examples,c.examples)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertTrue(DirectionCheck().restore(path,now=951))
            self.assertFalse(DirectionCheck().restore(path,now=86451))

    def test_old_calibration_format_cannot_be_restored_as_fresh_check(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'old.json'
            path.write_text(json.dumps(dict(band=43,trials=[],reference={})))
            self.assertFalse(DirectionCheck().restore(path,now=60))

    def test_explicit_correction_updates_only_the_chosen_direction_and_copies_data(self):
        c=DirectionCheck();samples=state()['recent_samples']
        self.assertTrue(c.correct('left',dict(samples=samples)))
        self.assertEqual(set(c.examples),{'left'})
        original=c.examples['left']['samples'][0]['ax']
        samples[0]['ax']=99
        self.assertEqual(c.examples['left']['samples'][0]['ax'],original)
        self.assertFalse(c.correct('invented',dict(samples=samples)))

    def test_arrow_key_is_not_quit_or_automatic_mode_toggle(self):
        read,write=os.pipe()
        try:
            os.write(write,b'\x1b[A')
            self.assertIsNone(read_key(read))
            self.assertIsNone(read_key(read))
            os.write(write,b'\x1b')
            self.assertEqual(read_key(read),'\x1b')
            os.write(write,b'q')
            self.assertEqual(read_key(read),'q')
        finally:
            os.close(read);os.close(write)
