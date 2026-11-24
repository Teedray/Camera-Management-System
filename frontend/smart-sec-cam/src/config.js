// The Docker entrypoint (docker-entrypoint.sh) rewrites the text "localhost:8443"
// in the built JavaScript to the real server address, so keep this exact string.
export const SERVER_URL = "https://localhost:8443";

// Run the front end with no backend: REACT_APP_USE_MOCK=1 npm start
// (login is skipped and fake recordings are generated; see src/api/mockRecordings.js).
export const USE_MOCK = process.env.REACT_APP_USE_MOCK === "1";
