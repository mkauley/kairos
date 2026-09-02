# Google Cloud Setup — Kairos

## Does it cost money?

**No.** The Google Calendar API is free and is not a billable API.

- Creating a Google Cloud project — free, no credit card required.
- Enabling the Calendar API — free.
- Creating OAuth credentials — free.
- Calendar API usage — free, quota of 1,000,000 queries/day (we'll use a
  handful). No paid tier, no billing account requirement for this API.

You are only charged in Google Cloud if you explicitly create a paid resource
(a VM, Cloud SQL, etc.). Enabling an API is not that. Nothing in this flow
asks for payment info.

## Setup steps

### 1. Create a project
- Go to https://console.cloud.google.com
- Top bar → project dropdown → **New Project**
- Name it `kairos` (or anything) → **Create** → select it once created

### 2. Enable the Calendar API
- Left menu → **APIs & Services → Library**
- Search "Google Calendar API" → click it → **Enable**

### 3. Configure the OAuth consent screen (Google Auth Platform)

**APIs & Services → OAuth consent screen** now opens the "Google Auth
Platform" overview. If it says *"Google Auth Platform not configured yet"*,
click **Get Started** and complete the wizard:

1. **App Information** — App name: `Kairos`, user support email: your
   email → **Next**
2. **Audience** — **External** → **Next**
3. **Contact Information** — your email → **Next**
4. **Finish** — check the box agreeing to the Google API Services User Data
   Policy → **Continue** → **Create**

After the wizard you land on the Google Auth Platform page with a left menu:
Overview, Branding, Audience, Clients, Data Access.

**Add yourself as a test user:**
- Left menu → **Audience**
- Under **Test users** → **Add users** → add your Google address → **Save**
- Publishing status stays **Testing** — that's what you want. A testing-mode
  app just shows an "unverified app" warning you click past, and refresh
  tokens expire every 7 days (irrelevant for the throwaway Flask sandbox;
  handled properly in the Kotlin app later).

### 4. Create OAuth credentials
- Left menu → **Clients** → **Create client**
  (or **APIs & Services → Credentials → Create Credentials → OAuth client ID**)
- Application type: **Desktop app**
- Name: `kairos-desktop` → **Create**
- Click **Download JSON**
- Save that file as `credentials.json` in the project root:
  `/home/mkeph/code/mkalendar/credentials.json`

### 5. Next
- Confirm `credentials.json` is in the project root.
- `.gitignore` must exclude it (and `token.json`, generated on first auth).
- Then build the Flask app and run the first real `/create` against the
  calendar.
