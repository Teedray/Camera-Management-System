import React from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { clockSecondsInTz, formatDate, formatTime } from "../utils/time";

// Start and end time for a clip, chosen inside the range that was searched.
export default function IntervalFields({ values, errors, onChange, posMs, tz, rangeStartMs, rangeEndMs }) {
  const inputProps = { inputLabel: { shrink: true }, htmlInput: { step: 1 } };
  return (
    <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: "1fr 1fr" }}>
      <Typography variant="body2" color="text.secondary" sx={{ gridColumn: "1 / -1" }}>
        {formatDate(rangeStartMs, tz)}. You searched {formatTime(rangeStartMs, tz, false)} to {formatTime(rangeEndMs, tz, false)}.
      </Typography>
      <TextField label="Start time" type="time" value={values.start} slotProps={inputProps}
                 onChange={(e) => onChange("start", e.target.value)}
                 error={Boolean(errors.start)} helperText={errors.start} />
      <TextField label="End time" type="time" value={values.end} slotProps={inputProps}
                 onChange={(e) => onChange("end", e.target.value)}
                 error={Boolean(errors.end)} helperText={errors.end} />
      <Button size="small" disabled={posMs == null} onClick={() => onChange("start", clockSecondsInTz(posMs, tz))}>
        Start at current position
      </Button>
      <Button size="small" disabled={posMs == null} onClick={() => onChange("end", clockSecondsInTz(posMs, tz))}>
        End at current position
      </Button>
    </Box>
  );
}
