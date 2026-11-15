# Today agenda

Today replaces the large Devices panel. Device connection indicators and **Devices ↗** remain in the header. The agenda shows current and upcoming events for the connected calendar's day and timezone, in chronological order. The transcript remains newest-first.

## Use

- **Calendars ↗** opens calendar selection and connection settings.
- Select up to five calendars; the primary calendar is selected initially.
- Click an event to open it in Google Calendar.
- **Open calendar ↗** opens the displayed day.
- Empty days, missing access, and stale cached data have distinct labels.

Calendar access is **read-only**. inLoop does not create events, send invitations, or change existing events. Task suggestions and existing speech processing remain separate.

## Google sign-in

The app uses a Google OAuth **Desktop app** client, a loopback callback, PKCE, and a single-use authorization state. Google authenticates the user in the browser; inLoop never asks for a Google password.

For another installation:

1. Enable the Google Calendar API in your Google Cloud project.
2. Configure the OAuth consent screen. For a personal testing project, add your Google account as a test user.
3. Create a Desktop app OAuth client and download its JSON file.
4. In Today, choose **Connect ↗**, select the JSON file, and **Continue with Google**.
5. Allow these read-only permissions:
   - `calendar.events.readonly`
   - `calendar.calendarlist.readonly`

The Google consent screen displays the project's branding, which may differ from the Desktop client's name. Creating a separate Desktop client does not rename other apps in that project.

You can also set `INLOOP_GOOGLE_OAUTH_CLIENT_FILE` in the private local environment to use an existing Desktop app JSON file. An API key for Gemini or Maps cannot authorize calendar access.

## Storage and sync

Credentials, refresh tokens, preferences and the last agenda are kept in ignored files under `logs/inloop-calendar-*.json`, with owner-only permissions. No token or client secret is returned to the browser. The callback route is local; authorization codes are not written to access logs.

The app refreshes approximately every minute, independently of caption streaming. It expands recurring instances, respects cancellations and declined invitations, handles all-day dates in the calendar timezone, and keeps cached data when a refresh fails. Last-sync labels distinguish cached data from a fresh sync. Cached events from a previous date are not shown as today's agenda.

**Disconnect from inLoop** deletes its locally stored tokens and cached calendar data. It leaves the OAuth client configuration available for reconnecting. You can separately remove the app's grant in your Google Account settings.
