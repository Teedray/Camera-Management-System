import React from "react";
import { useNavigate } from "react-router-dom";

import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';

import { USE_MOCK } from "../config";

import "./Register.css"

const SERVER_URL = "https://localhost:8443"
const REGISTER_ENDPOINT = "/api/auth/register"


export default function Register(props) {
    const [username, setUsername] = React.useState("");
    const [password, setPassword] = React.useState("");
    const navigate = useNavigate();

    React.useEffect(() => {
        // Mock mode has demo accounts already; there is nothing to register.
        if (USE_MOCK) {
            navigate('/');
        }
    }, [navigate]);

    function handleRegistration() {
        // Submit username and password
        const url = SERVER_URL + REGISTER_ENDPOINT;
        const payload = {
            "username": username,
            "password": password,
        }
        const requestOptions = {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        };
        fetch(url, requestOptions)
        .then(response => response.json())
        .then(data => handleRegisterResponse(data));  
    }

    function handleRegisterResponse(data) {
        if (data.status === "OK") {
            // Navigate to Login page
            navigate('/', {state: { username: username }});
        }
        else {
            // TODO: Show error message on UI somewhere
            console.log("Registration failed")
        }
    }

    return (
      <div className="Register auth-page">
        <div className="auth-art" aria-hidden="true">
          <div className="auth-brand"><div className="auth-logo">◉</div><span>Sentinel<span className="auth-brand-accent">Vision</span></span></div>
          <div className="auth-art-content"><span className="auth-eyebrow">SECURITY, REIMAGINED</span><h2>Every camera.<br/>One clear view.</h2><p>A smarter workspace for monitoring, reviewing and managing your security operations.</p><div className="auth-art-line"/></div>
          <span className="auth-art-bottom">SECURE VIDEO MANAGEMENT PLATFORM</span>
        </div>
        <main className="auth-form-side">
          <div className="auth-card">
            <div className="auth-mobile-brand">◉ SentinelVision</div>
            <span className="auth-eyebrow">ACCOUNT ACCESS</span>
            <Typography component="h1" variant="h4" sx={{fontWeight:800,letterSpacing:'-.05em',mt:1,mb:.8}}>Create account</Typography>
            <Typography color="text.secondary" sx={{fontSize:14,mb:4}}>Set up your security workspace</Typography>
            <Box component="form" noValidate onSubmit={event => {event.preventDefault(); handleRegistration();}} sx={{display:'grid',gap:2}}>
              <TextField required fullWidth id="username" label="Username" autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} />
              <TextField required fullWidth id="password" label="Password" type="password" autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)} />
              <Button fullWidth variant="contained" size="large" type="submit" sx={{mt:1,py:1.4}}>Register</Button>
              
              
            </Box>
            <p className="auth-footer">Protected access · Smart Security Camera</p>
          </div>
        </main>
      </div>
    );
}
