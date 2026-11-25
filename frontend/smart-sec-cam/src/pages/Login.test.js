import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CookiesProvider } from "react-cookie";

import Login from "./Login";

jest.mock("../config", () => ({ SERVER_URL: "https://localhost:8443", USE_MOCK: true }));
const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({ useNavigate: () => mockNavigate }), { virtual: true });

const signedOut = () => { document.cookie = "token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/"; };
const show = () => render(<CookiesProvider><Login /></CookiesProvider>);
async function signIn(username, password) {
  if (username) await userEvent.type(screen.getByLabelText(/^Username/), username);
  if (password) await userEvent.type(screen.getByLabelText(/^Password/), password);
  await userEvent.click(screen.getByRole("button", { name: "Login" }));
}

beforeEach(() => {
  signedOut();
  mockNavigate.mockClear();
  global.fetch = jest.fn();
});

describe("Login (mock mode)", () => {
  test("shows the demo accounts and never contacts a server", () => {
    show();
    expect(screen.getByText(/Demo accounts/)).toHaveTextContent("owner (admin), manager1 (manager), viewer1 (viewer)");
    expect(global.fetch).not.toHaveBeenCalled();
    expect(screen.queryByText(/Failed to fetch/)).not.toBeInTheDocument();
  });

  test("a correct login saves the cookie and opens the search page", async () => {
    show();
    await signIn("owner", "password");
    expect(mockNavigate).toHaveBeenCalledWith("/search");
    expect(decodeURIComponent(document.cookie)).toContain("token=mock-token:owner");
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test("each demo account gets its own token", async () => {
    show();
    await signIn("viewer1", "password");
    expect(decodeURIComponent(document.cookie)).toContain("token=mock-token:viewer1");
  });

  test("a wrong password shows a message and stays on the login page", async () => {
    show();
    await signIn("owner", "nope");
    expect(await screen.findByText("Incorrect username or password.")).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
    expect(document.cookie).not.toContain("token=mock");
  });

  test("an unknown user is turned away the same way", async () => {
    show();
    await signIn("stranger", "password");
    expect(await screen.findByText("Incorrect username or password.")).toBeInTheDocument();
  });

  test("empty fields ask for both", async () => {
    show();
    await signIn("", "");
    expect(await screen.findByText("Enter your username and password.")).toBeInTheDocument();
  });

  test("already signed in goes straight to the search page", () => {
    document.cookie = "token=mock-token:owner; path=/";
    show();
    expect(mockNavigate).toHaveBeenCalledWith("/search");
  });
});
