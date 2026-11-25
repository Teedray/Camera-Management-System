import React from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import SearchIcon from "@mui/icons-material/Search";

import { clockInTz, todayInTz } from "../utils/time";

const TIME = /^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/;

// Same rules as the server (SR-03-01), so most mistakes are caught before a request is sent.
export function validateSearch(values) {
  const errors = {};
  if (!values.camera) errors.camera = "Select a camera.";
  if (!values.date) errors.date = "Choose a date.";
  if (!TIME.test(values.start || "")) errors.start = "Enter the start time.";
  if (!TIME.test(values.end || "")) errors.end = "Enter the end time.";
  if (!errors.start && !errors.end && values.end <= values.start) {
    errors.end = "The end time must be after the start time.";
  }
  return errors;
}

// Default to the last hour of today (never crossing midnight; searches are for one day).
export function defaultValues(now = new Date()) {
  const end = clockInTz(undefined, now);
  const startMinutes = Math.max(0, Number(end.slice(0, 2)) * 60 + Number(end.slice(3)) - 60);
  const start = `${String(Math.floor(startMinutes / 60)).padStart(2, "0")}:${String(startMinutes % 60).padStart(2, "0")}`;
  return { camera: "", date: todayInTz(undefined, now), start, end };
}

export default function SearchForm({ cameras, loading, serverError, onSearch, onEdit, initialValues }) {
  const [values, setValues] = React.useState(() => ({ ...defaultValues(), ...initialValues }));
  const [errors, setErrors] = React.useState({});

  function update(field) {
    return (event) => {
      setValues((v) => ({ ...v, [field]: event.target.value }));
      setErrors((e) => ({ ...e, [field]: undefined }));
      if (onEdit) onEdit();
    };
  }

  function submit(event) {
    event.preventDefault();
    const found = validateSearch(values);
    setErrors(found);
    if (Object.keys(found).length === 0) onSearch(values);
  }

  const problem = (field) => errors[field] || (serverError && serverError.field === field ? serverError.message : "");
  const shrink = { inputLabel: { shrink: true } };

  return (
    <Box component="form" onSubmit={submit} noValidate aria-label="Search recordings"
         sx={{ display: "grid", gap: 2, gridTemplateColumns: "1fr 1fr" }}>
      <TextField select label="Camera" value={values.camera} onChange={update("camera")}
                 error={Boolean(problem("camera"))} helperText={problem("camera")}
                 disabled={!cameras || cameras.length === 0} sx={{ gridColumn: "1 / -1" }}
                 slotProps={{ select: { displayEmpty: true }, inputLabel: { shrink: true } }}>
        <MenuItem value="" disabled>
          {cameras && cameras.length === 0 ? "No cameras available" : "Choose a camera"}
        </MenuItem>
        {(cameras || []).map((c) => (
          <MenuItem key={c.name} value={c.name}>{c.name}</MenuItem>
        ))}
      </TextField>
      <TextField label="Date" type="date" value={values.date} onChange={update("date")}
                 error={Boolean(problem("date"))} helperText={problem("date")}
                 slotProps={shrink} sx={{ gridColumn: "1 / -1" }} />
      <TextField label="Start time" type="time" value={values.start} onChange={update("start")}
                 error={Boolean(problem("start"))} helperText={problem("start")} slotProps={shrink} />
      <TextField label="End time" type="time" value={values.end} onChange={update("end")}
                 error={Boolean(problem("end"))} helperText={problem("end")} slotProps={shrink} />
      <Button type="submit" variant="contained" size="large" startIcon={<SearchIcon />}
              disabled={loading} sx={{ gridColumn: "1 / -1" }}>
        {loading ? "Searching…" : "Search"}
      </Button>
    </Box>
  );
}
