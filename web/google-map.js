/* Google satellite map, upgraded to interactive 3D when a localhost browser key is configured. */
export class GoogleLocationMap {
  constructor(container) { this.container=container;this.identity='';this.fix=null;this.map=null;this.marker=null;this.accuracy=null;this.ready=null;this.failed3D=false;this.userAdjusted=false; }
  clear(message='No matching GPS fix') {
    this.fix=null;this.identity='';this.map=null;this.marker=null;this.accuracy=null;this.userAdjusted=false;
    const empty=document.createElement('p');empty.className='map-message';empty.textContent=message;
    this.container.replaceChildren(empty);this.container.dataset.provider='google';
  }
  update(fix) {
    this.fix=fix;
    const identity=JSON.stringify([fix.latitude,fix.longitude,fix.accuracy]);
    if(identity===this.identity)return;
    this.identity=identity;
    if(this.map){this.move3D(fix);return;}
    this.embed(fix);
    if(!this.ready&&!this.failed3D)this.ready=this.upgrade3D().catch(()=>{this.failed3D=true;}).finally(()=>{this.ready=null;});
  }
  embed(fix) {
    if(!fix)return;
    const frame=document.createElement('iframe');frame.title='Google satellite map of the phone GPS location';
    frame.referrerPolicy='strict-origin-when-cross-origin';frame.allowFullscreen=true;
    const query=new URLSearchParams({q:`${fix.latitude},${fix.longitude}`,z:fix.accuracy>1000?'14':fix.accuracy>200?'16':'18',t:'k',output:'embed'});
    frame.src='https://maps.google.com/maps?'+query;frame.className='google-location-map';
    this.container.replaceChildren(frame);this.container.dataset.provider='google-satellite';
  }
  async upgrade3D() {
    const response=await fetch('/api/maps-config');if(!response.ok)return;
    const config=await response.json();if(!config.key)return;
    if(!window.google?.maps){
      await new Promise((resolve,reject)=>{
        let finished=false;
        const timer=setTimeout(()=>done(Error('Google Maps timed out')),12000);
        const done=error=>{if(finished)return;finished=true;clearTimeout(timer);error?reject(error):resolve();};
        window.__inLoopGoogleReady=()=>done();
        window.gm_authFailure=()=>{this.failed3D=true;this.map=null;this.embed(this.fix);done(Error('Google Maps key is not authorized for this origin'));};
        const script=document.createElement('script');script.async=true;script.referrerPolicy='strict-origin-when-cross-origin';
        script.src='https://maps.googleapis.com/maps/api/js?'+new URLSearchParams({key:config.key,callback:'__inLoopGoogleReady',loading:'async',v:'weekly'});
        script.onerror=()=>done(Error('Google Maps could not load'));document.head.append(script);
      });
    }
    const [{Map3DElement,Marker3DElement,Polygon3DElement},{PinElement}]=await Promise.all([google.maps.importLibrary('maps3d'),google.maps.importLibrary('marker')]);
    if(!this.fix||this.failed3D)return;
    const f=this.fix;const point={lat:f.latitude,lng:f.longitude,altitude:0};
    const map=new Map3DElement({center:point,range:Math.max(700,Math.min(5000,f.accuracy*4)),fov:22.5,tilt:0,heading:0,mode:'SATELLITE',defaultUIHidden:true,gestureHandling:'COOPERATIVE'});
    map.style.width='100%';map.style.height='100%';
    const accuracy=new Polygon3DElement({path:accuracyPath(f),fillColor:'#ffffff2e',strokeColor:'#ffffffb3',strokeWidth:1,drawsOccludedSegments:true});
    const marker=new Marker3DElement({position:point,sizePreserved:true});
    marker.append(new PinElement({background:'#202124',borderColor:'#ffffff',glyphColor:'#ffffff',scale:.8}));
    map.append(accuracy,marker);
    // GPS updates should not undo a camera position chosen by the user.
    for(const event of ['pointerdown','wheel','touchstart'])map.addEventListener(event,()=>{this.userAdjusted=true;},{passive:true});
    map.addEventListener('gmp-error',()=>{this.failed3D=true;this.map=null;this.embed(this.fix);});
    this.map=map;this.marker=marker;this.accuracy=accuracy;this.container.replaceChildren(map);this.container.dataset.provider='google-3d';
  }
  move3D(fix) {
    const point={lat:fix.latitude,lng:fix.longitude,altitude:0};
    this.marker.position=point;
    if(this.accuracy)this.accuracy.path=accuracyPath(fix);
    if(!this.userAdjusted){
      this.map.center=point;
      this.map.range=Math.max(700,Math.min(5000,fix.accuracy*4));
    }
  }
}

// Geographic accuracy boundary, in meters, matching the website renderer.
function accuracyPath(fix){
  const distance=Math.max(0,fix.accuracy)/6378137;
  const latitude=fix.latitude*Math.PI/180,longitude=fix.longitude*Math.PI/180;
  return Array.from({length:49},(_,index)=>{
    const bearing=2*Math.PI*index/48;
    const lat=Math.asin(Math.sin(latitude)*Math.cos(distance)+Math.cos(latitude)*Math.sin(distance)*Math.cos(bearing));
    const lng=longitude+Math.atan2(Math.sin(bearing)*Math.sin(distance)*Math.cos(latitude),Math.cos(distance)-Math.sin(latitude)*Math.sin(lat));
    return {lat:lat*180/Math.PI,lng:lng*180/Math.PI};
  });
}

// Resolve a city only when entering a new area, not for every GPS packet.
const cityCache=new Map();
export async function locationCity(fix){
  if(typeof fix.city==='string'&&fix.city.trim())return fix.city.trim();
  const area=`${fix.latitude.toFixed(2)},${fix.longitude.toFixed(2)}`;
  if(cityCache.has(area))return cityCache.get(area);
  const pending=(async()=>{
    const cached=sessionStorage.getItem('inloop-city:'+area);
    if(cached)return cached;
    const query=new URLSearchParams({lat:fix.latitude,lon:fix.longitude,limit:1,lang:'en'});
    const response=await fetch('https://photon.komoot.io/reverse?'+query,{signal:AbortSignal.timeout(5000),referrerPolicy:'strict-origin-when-cross-origin'});
    if(!response.ok)return '';
    const result=await response.json();const p=result.features?.[0]?.properties||{};
    const city=p.city||p.town||p.village||p.county||'';
    if(city)sessionStorage.setItem('inloop-city:'+area,city);
    return city;
  })().catch(()=> '');
  cityCache.set(area,pending);
  if(cityCache.size>24)cityCache.delete(cityCache.keys().next().value);
  return pending;
}
