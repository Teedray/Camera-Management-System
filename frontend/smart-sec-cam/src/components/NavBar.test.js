import { render, screen, within } from "@testing-library/react";
import { CookiesProvider } from "react-cookie";
import userEvent from "@testing-library/user-event";

import NavBar from "./NavBar";
import useMe from "../hooks/useMe";

jest.mock("../config", () => ({ SERVER_URL: "https://localhost:8443", USE_MOCK: true }));
const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  useLocation: () => ({ pathname: "/incidents" }),
}), { virtual: true });
jest.mock("../hooks/useMe", () => ({ __esModule: true, default: jest.fn() }));

beforeEach(() => mockNavigate.mockClear());
const show = (ui) => render(<CookiesProvider>{ui}</CookiesProvider>);

describe("NavBar", () => {
  test("administrators see every page, including Admin", () => {
    useMe.mockReturnValue({ role: "admin" });
    show(<NavBar token="t" />);
    const nav = screen.getByRole("navigation", { name: "Main" });
    ["Dashboard", "Live", "Search", "Incidents", "Exports", "Merge", "Videos", "Status",
     "Administration", "Cloud", "Storage", "Audit logs"].forEach((label) =>
      expect(within(nav).getByRole("button", { name: label })).toBeInTheDocument());
  });

  test("other roles do not see Admin", () => {
    useMe.mockReturnValue({ role: "viewer" });
    show(<NavBar token="t" />);
    const nav = screen.getByRole("navigation", { name: "Main" });
    ["Exports", "Merge", "Administration", "Cloud", "Storage", "Audit logs"].forEach((label) =>
      expect(within(nav).queryByRole("button", { name: label })).not.toBeInTheDocument());
    expect(within(nav).getByRole("button", { name: "Search" })).toBeInTheDocument();
  });

  test("marks the current page and navigates when a link is pressed", async () => {
    useMe.mockReturnValue({ role: "manager" });
    show(<NavBar token="t" />);
    expect(screen.getByRole("button", { name: "Incidents" })).toHaveAttribute("aria-current", "page");
    await userEvent.click(screen.getByRole("button", { name: "Exports" }));
    expect(mockNavigate).toHaveBeenCalledWith("/exports");
  });

  test("on a phone the menu button opens a list of the same pages", async () => {
    useMe.mockReturnValue({ role: "admin" });
    show(<NavBar token="t" />);
    await userEvent.click(screen.getByRole("button", { name: "Open navigation menu" }));
    const menu = await screen.findByRole("list", { name: "Menu" });
    expect(menu).toHaveTextContent("Administration");
    await userEvent.click(within(menu).getByRole("button", { name: "Status" }));
    expect(mockNavigate).toHaveBeenCalledWith("/status");
  });

  test("shows who is signed in, and signing out clears the login and returns to the login page", async () => {
    useMe.mockReturnValue({ role: "admin", username: "owner" });
    document.cookie = "token=abc; path=/";
    show(<NavBar token="t" />);
    expect(screen.getByText("owner · admin")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(mockNavigate).toHaveBeenCalledWith("/");
    expect(document.cookie).not.toContain("token=");
  });
});
