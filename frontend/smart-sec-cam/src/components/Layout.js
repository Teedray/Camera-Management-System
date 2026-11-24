import React from "react";
import Box from "@mui/material/Box";

import NavBar from "./NavBar";
import StatusBanner from "./StatusBanner";

// The frame shared by the new pages: navigation bar, warnings, then the content centred and
// padded for phones as well as desktops.
export default function Layout({ token, children }) {
  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <NavBar token={token} />
      <StatusBanner token={token} />
      <Box component="main" sx={{ p: { xs: 2, md: 4 }, maxWidth: 1540, mx: "auto" }}>
        {children}
      </Box>
    </Box>
  );
}
