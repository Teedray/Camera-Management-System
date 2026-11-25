import React from "react";
import { useNavigate } from "react-router-dom";

import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import Alert from '@mui/material/Alert';
import { useCookies } from 'react-cookie';

import { USE_MOCK } from "../config";
import { MOCK_PASSWORD, mockAccounts, mockLogin } from "../api/mockAuth";

import { validateToken } from "../utils/ValidateToken";

import "./Login.css"


const SERVER_URL = "https://localhost:8443"
const AUTH_ENDPOINT = "/api/auth/login"
const NUM_USERS_ENDPOINT = "/api/auth/num-users"
const REFRESH_TOKEN_ENDPOINT = "/api/token/refresh"
const NETWORK_ERROR = "Could not reach the server. Check the connection and try again."


export default function Login(props) {
    const [username, setUsername] = React.useState("");
    const [password, setPassword] = React.useState("");
    const [token, setToken] = React.useState("");
    const [hasRegisteredUser, setHasRegisteredUser] = React.useState(null);
    const [hasValidToken, setHasValidToken] = React.useState(null);
    const [busy, setBusy] = React.useState(false);
    const [error, setError] = React.useState("");
    const [cookies, setCookie] = useCookies(["token"]);
    const navigate = useNavigate();

    React.useEffect(() => {
        if (USE_MOCK) {
            // Mock mode has no server. If already signed in, go straight to the search page.
            if (cookies.token) {
                navigate('/search');
            }
            return;
        }
        checkServerHasUser();
    }, []);


    React.useEffect(() => {
        if (hasRegisteredUser == null) {
            return;
        }
        if (hasRegisteredUser) {
            // Check cookies to see if we have a JWT. If so, auto-redirect to video stream page
            const cachedToken = cookies.token;
            // Validate token
            validateToken(cachedToken, setHasValidToken);
        }
        else if (hasRegisteredUser === false) {
            navigate('/register');
        }
    }, [hasRegisteredUser]);

    React.useEffect(() => {
        const cachedToken = cookies.token;
        if (cachedToken != null && hasValidToken) {
            // Refresh token
            refreshToken(cachedToken);
        }
    }, [hasValidToken])

    React.useEffect(() => {
        if (token != null && hasValidToken) {
            // Already signed in: the same landing page as a fresh login.
            navigate('/dashboard');
        }
    }, [token])

    function checkServerHasUser() {
        const url = SERVER_URL + NUM_USERS_ENDPOINT;
        fetch(url)
            .then(response => response.json())
            .then(data => handleCheckServerHasUserResponse(data))
            .catch(() => setError(NETWORK_ERROR));
    }

    function handleCheckServerHasUserResponse(data) {
        setHasRegisteredUser(data["users"] > 0)
    }

    function refreshToken(token) {
        const url = SERVER_URL + REFRESH_TOKEN_ENDPOINT;
        const payload = {
            "token": token
        }
        const requestOptions = {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        };
        fetch(url, requestOptions)
            .then(response => response.json())
            .then(data => handleRefreshTokenResponse(data)); 
    }

    function handleRefreshTokenResponse(data){
        if (data.status === "OK") {
            setToken(data["token"]);
            // Write token to cookie
            setCookie("token", data["token"], {path: "/"})
        }
        else {
            // TODO: Show error message on UI somewhere
            console.log("Token refresh failed");
        }
    }

    function handleLogin() {
        if (busy) return;
        setError("");
        if (!username.trim() || !password) {
            setError("Enter your username and password.");
            return;
        }
        if (USE_MOCK) {
            const result = mockLogin(username.trim(), password);
            if (result.status === "OK") {
                setCookie("token", result.token, {path: "/"});
                navigate('/search');
            }
            else {
                setError(result.error);
            }
            return;
        }
        setBusy(true);
        // Submit username and password
        const url = SERVER_URL + AUTH_ENDPOINT;
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
        .then(data => handleLoginResponse(data))
        .catch(() => setError(NETWORK_ERROR)).finally(() => setBusy(false));
    };

    function handleLoginResponse(data) {
        if (data.status === "OK") {
            setToken(data["token"]);
            // Write token to cookie
            setCookie("token", data["token"], {path: "/"})
            // Navigate to App page,
            try { sessionStorage.setItem('sentinel-last-activity', String(Date.now())); } catch(e) {}
            navigate('/dashboard');
        }
        else {
            setError("Incorrect username or password.");
            console.log("Login failed")
        }
    }

    return (
      <div className="Login auth-page">
        <div className="auth-art" aria-hidden="true">
          <div className="auth-brand"><div className="auth-logo">◉</div><span>Sentinel<span className="auth-brand-accent">Vision</span></span></div>
          <div className="auth-art-content"><span className="auth-eyebrow">SECURITY, REIMAGINED</span><h2>Every camera.<br/>One clear view.</h2><p>A smarter workspace for monitoring, reviewing and managing your security operations.</p><div className="auth-art-line"/></div>
          <span className="auth-art-bottom">SECURE VIDEO MANAGEMENT PLATFORM</span>
        </div>
        <main className="auth-form-side">
          <div className="auth-card">
            <div className="auth-mobile-brand">◉ SentinelVision</div>
            <span className="auth-eyebrow">ACCOUNT ACCESS</span>
            <Typography component="h1" variant="h4" sx={{fontWeight:800,letterSpacing:'-.05em',mt:1,mb:.8}}>Welcome back</Typography>
            <Typography color="text.secondary" sx={{fontSize:14,mb:4}}>Sign in to your security workspace</Typography>
            <Box component="form" noValidate onSubmit={event => {event.preventDefault(); handleLogin();}} sx={{display:'grid',gap:2}}>
              <TextField required fullWidth id="username" label="Username" autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} />
              <TextField required fullWidth id="password" label="Password" type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} />
              <Button fullWidth variant="contained" size="large" type="submit" disabled={busy} sx={{mt:1,py:1.4}}>{busy ? "Signing in…" : "Login"}</Button>
              {error && <Alert severity="error">{error}</Alert>}
              {USE_MOCK && <Alert severity="info" sx={{fontSize:12}}>Demo accounts (mock mode): {mockAccounts().map(a => `${a.username} (${a.role})`).join(", ")}. Password for all: {MOCK_PASSWORD}</Alert>}
            </Box>
            <p className="auth-footer">Protected access · Smart Security Camera</p>
          </div>
        </main>
      </div>
    );
}
