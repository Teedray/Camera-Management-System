import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CookiesProvider } from "react-cookie";

import Login from "./Login";

// Real mode: the page talks to the server, so these answer on its behalf.
jest.mock("../config", () => ({ SERVER_URL: "https://localhost:8443", USE_MOCK: false }));
const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({ useNavigate: () => mockNavigate }), { virtual: true });

const reply = (body) => Promise.resolve({ json: () => Promise.resolve(body) });
function server({ login }) {
  global.fetch = jest.fn((url) => {
    if (url.endsWith("/api/auth/num-users")) return reply({ users: 1 });
    if (url.endsWith("/api/token/validate")) return reply({ status: "ERROR" });
    if (url.endsWith("/api/auth/login")) return reply(login);
    return reply({});
  });
}
const show = () => render(<CookiesProvider><Login /></CookiesProvider>);
async function signIn() {
  await userEvent.type(screen.getByLabelText(/^Username/), "owner");
  await userEvent.type(screen.getByLabelText(/^Password/), "secret");
  await userEvent.click(screen.getByRole("button", { name: "Login" }));
}

beforeEach(() => mockNavigate.mockClear());

describe("Login (real server)", () => {
  test("a wrong password is now shown on the page", async () => {
    server({ login: { status: "ERROR" } });
    show();
    await signIn();
    expect(await screen.findByText("Incorrect username or password.")).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  test("a correct login opens the dashboard", async () => {
    server({ login: { status: "OK", token: "abc" } });
    show();
    await signIn();
    await screen.findByRole("button", { name: "Login" });
    expect(mockNavigate).toHaveBeenCalledWith("/dashboard");
  });

  test("an unreachable server shows a message instead of crashing the page", async () => {
    global.fetch = jest.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    show();
    expect(await screen.findByText(/Could not reach the server/)).toBeInTheDocument();
  });
});

test("legacy viewer can submit an empty username with its password", async () => {
  server({ login: { status: "OK", token: "legacy-token" } });
  show();
  await userEvent.type(screen.getByLabelText(/^Password/), "secret");
  await userEvent.click(screen.getByRole("button", { name: "Login" }));
  expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("/api/auth/login"),
    expect.objectContaining({body: JSON.stringify({username: "", password: "secret"})}));
});
