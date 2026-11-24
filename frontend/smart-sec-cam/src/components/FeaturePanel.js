import React from 'react';
import { Alert, Box, Button, CircularProgress, Paper, Typography } from '@mui/material';
export function FeaturePanel({title, detail, children, action, busy=false}) {
  return <Paper component="section" sx={{p:2.5, mb:2}} aria-label={title}>
    <Box sx={{display:'flex',gap:2,alignItems:'center',justifyContent:'space-between',flexWrap:'wrap',mb:1.5}}>
      <Box><Typography variant="h6">{title}</Typography>{detail && <Typography variant="body2" color="text.secondary">{detail}</Typography>}</Box>
      {action}
    </Box>
    {busy && <CircularProgress size={20} aria-label="Loading"/>}
    {children}
  </Paper>;
}
export function NotConnected({name, detail}) {
  return <Alert severity="warning" sx={{mt:1}}>{name} cannot be verified because the running backend does not expose this API. {detail || 'Values are not assumed, and changes cannot be saved until the service is connected.'}</Alert>;
}
export function RetryError({error, onRetry}) {
  if (!error) return null;
  return <Alert severity="error" sx={{mb:2}} action={onRetry?<Button onClick={onRetry} color="inherit" size="small">Retry</Button>:undefined}>{error}</Alert>;
}
export function InfoGrid({items}) {
  return <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr 1fr',lg:'repeat(4, 1fr)'},gap:1.5}}>{items.map(item=><Paper key={item.label} variant="outlined" sx={{p:2}}><Typography color="text.secondary" variant="caption">{item.label}</Typography><Typography variant="h6">{item.value ?? 'Unknown'}</Typography>{item.detail && <Typography color="text.secondary" variant="caption">{item.detail}</Typography>}</Paper>)}</Box>;
}
