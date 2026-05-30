# Frontend pages

`App.jsx` is intentionally a tiny entrypoint. The current interview/dashboard implementation is kept in `CodeVoirApp.jsx` to preserve behavior while making the root file clean.

Suggested next split, once the demo is stable:

- `WelcomePage.jsx`
- `DashboardPage.jsx`
- `InterviewPage.jsx`
- `ReportsPage.jsx`
- `FeedbackPages/`
- `hooks/useInterviewSession.js`
- `api/codevoirClient.js`
