import { render, screen, waitFor } from "@testing-library/react";
import { CookiesProvider } from "react-cookie";

import App from "./App";
import useMe from "./hooks/useMe";
import { resetMock } from "./api/mockBackend";

// The live monitoring page (/stream) in mock mode: no server, no camera streams.
// react-router-dom 7 is ESM-only and Jest under react-scripts 5 cannot load it, so
// it is mocked here as in the other page tests; the production build uses it as normal.
jest.mock("./config", () => ({ SERVER_URL: "https://localhost:8443", USE_MOCK: true }));
const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  useLocation: () => ({ pathname: "/stream" }),
}), { virtual: true });
jest.mock("./hooks/useMe", () => ({ __esModule: true, default: jest.fn() }));
jest.mock("socket.io-client", () => () => ({ on: jest.fn(), emit: jest.fn(), off: jest.fn(), disconnect: jest.fn(), connected: false }));

const show = () => render(<CookiesProvider><App /></CookiesProvider>);

beforeEach(() => {
  resetMock();
  mockNavigate.mockClear();
  document.cookie = "token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

test("a signed-in viewer sees only their assigned cameras on the live page", async () => {
  document.cookie = "token=mock-token:viewer1; path=/";
  useMe.mockReturnValue({ id: "u3", username: "viewer1", role: "viewer" });
  show();
  expect(await screen.findByRole("heading", { name: "Live camera monitoring" })).toBeInTheDocument();
  expect(await screen.findByText("Assigned cameras (1)")).toBeInTheDocument();
  expect(screen.getAllByText("CAM_AISLES").length).toBeGreaterThan(0);
  expect(screen.queryByText("CAM_DISPENSARY")).not.toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
});

test("a visitor who is not signed in is sent to the login page", async () => {
  useMe.mockReturnValue(null);
  show();
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/"));
  expect(screen.queryByRole("heading", { name: "Live camera monitoring" })).not.toBeInTheDocument();
});
