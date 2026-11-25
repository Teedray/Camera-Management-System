import { mock } from "./mockBackend";

// Everyone in mock mode signs in with this password. It only exists in the mock; the real server checks real accounts.
export const MOCK_PASSWORD = "password";

// The demo accounts are the users on the mock Admin page, so changing a role there changes what that login can do.
export const mockAccounts = () => mock.listUsers().map((u) => ({ username: u.username, role: u.role }));

export function mockLogin(username, password) {
  const account = mock.listUsers().find((u) => u.username === username);
  if (!account || password !== MOCK_PASSWORD) {
    return { status: "ERROR", error: "Incorrect username or password." };
  }
  return { status: "OK", token: `mock-token:${username}` };
}
