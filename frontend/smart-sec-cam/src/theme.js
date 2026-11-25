import { createTheme } from "@mui/material/styles";

// Shared application theme: components keep their existing APIs and mock data.
const theme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: "#648cff", contrastText: "#ffffff" },
    secondary: { main: "#38c9df" },
    background: { default: "#0a101c", paper: "#131e2e" },
    text: { primary: "#ecf3ff", secondary: "#94a5be" },
    divider: "rgba(148, 163, 184, .15)",
    success: { main: "#34d399" },
    warning: { main: "#fbbf24" },
    error: { main: "#fb7185" },
  },
  shape: { borderRadius: 14 },
  typography: {
    fontFamily: 'Inter, "Segoe UI", system-ui, sans-serif',
    h5: { fontWeight: 750, letterSpacing: "-0.035em" },
    h6: { fontWeight: 700, letterSpacing: "-0.02em" },
    button: { fontWeight: 650, textTransform: "none" },
  },
  components: {
    MuiCssBaseline: { styleOverrides: { body: { backgroundColor: "#0a101c" } } },
    MuiPaper: { styleOverrides: { root: { backgroundImage: "none", border: "1px solid rgba(148,163,184,.12)", boxShadow: "0 12px 30px rgba(0,0,0,.12)" } } },
    MuiCard: { styleOverrides: { root: { backgroundImage: "none", border: "1px solid rgba(148,163,184,.12)" } } },
    MuiButton: { defaultProps: { disableElevation: true }, styleOverrides: { root: { borderRadius: 9, paddingInline: 15, minHeight: 36 }, contained: { background: "linear-gradient(135deg,#577bfa,#3b63ec)", color: "white" }, outlined: { borderColor: "rgba(139,163,205,.3)" } } },
    MuiTextField: { defaultProps: { variant: "outlined" } },
    MuiOutlinedInput: { styleOverrides: { root: { borderRadius: 10, backgroundColor: "rgba(8,16,29,.38)" } } },
    MuiDialog: { styleOverrides: { paper: { background: "#172338" } } },
    MuiTabs: { styleOverrides: { indicator: { height: 3, borderRadius: 3 } } },
    MuiChip: { styleOverrides: { root: { borderRadius: 7, fontWeight: 600 } } },
  },
});
export default theme;
