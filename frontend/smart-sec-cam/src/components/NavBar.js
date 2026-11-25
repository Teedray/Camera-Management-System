import React from 'react';
import { useLocation,useNavigate } from 'react-router-dom';import { useCookies } from 'react-cookie';
import { AppBar,Box,Toolbar,Typography,Button,Drawer,IconButton,List,ListItemButton,ListItemText,Avatar,Chip } from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';import VideocamOutlinedIcon from '@mui/icons-material/VideocamOutlined';import LogoutOutlinedIcon from '@mui/icons-material/LogoutOutlined';
import useMe from '../hooks/useMe';import { canManageFootage,canManageSystem } from '../utils/permissions';
const LINKS=[
 {label:'Dashboard',path:'/dashboard'}, {label:'Live',path:'/stream'}, {label:'Search',path:'/search'},
 {label:'Incidents',path:'/incidents'}, {label:'Exports',path:'/exports',edit:true}, {label:'Merge',path:'/merge',edit:true},
 {label:'Videos',path:'/videos'}, {label:'Status',path:'/status'},
 {label:'Administration',path:'/admin',admin:true},{label:'Cloud',path:'/cloud',admin:true},
 {label:'Storage',path:'/storage',admin:true},{label:'Audit logs',path:'/activity',admin:true}
];
export default function NavBar({token}){
 const navigate=useNavigate(),location=useLocation(),me=useMe(token),[, ,removeCookie]=useCookies(['token']);const [open,setOpen]=React.useState(false);
 const links=LINKS.filter(l=>(!l.admin||canManageSystem(me?.role))&&(!l.edit||canManageFootage(me?.role)));
 const go=(path)=>{setOpen(false);navigate(path);};
 const signOut=()=>{setOpen(false);removeCookie('token',{path:'/'});navigate('/');};
 return <>
  <AppBar position="sticky" elevation={0} sx={{bgcolor:'#101a2a',borderBottom:'1px solid rgba(148,163,184,.15)',zIndex:1200}}><Toolbar sx={{minHeight:'72px !important',px:{xs:1.5,md:2},gap:1.5}}>
   <IconButton aria-label="Open navigation menu" sx={{display:{md:'none'}}} onClick={()=>setOpen(true)}><MenuIcon/></IconButton>
   <Box sx={{display:'flex',alignItems:'center',gap:1,flexShrink:0}}><Box sx={{display:'grid',placeItems:'center',width:36,height:36,borderRadius:2,bgcolor:'primary.main'}}><VideocamOutlinedIcon sx={{color:'#fff'}}/></Box><Box><Typography sx={{fontWeight:800,fontSize:15,lineHeight:1.2}}>Sentinel<span style={{color:'#8ba8ff'}}>Vision</span></Typography><Typography sx={{fontSize:9,color:'text.secondary',letterSpacing:'.14em'}}>SECURITY CONSOLE</Typography></Box></Box>
   <Box component="nav" aria-label="Main navigation" sx={{display:{xs:'none',md:'flex'},alignItems:'center',gap:.4,flex:1,overflowX:'auto',py:1,scrollbarWidth:'thin'}}>{links.map(l=><Button key={l.path} aria-current={location.pathname===l.path?'page':undefined} onClick={()=>go(l.path)} size="small" sx={{color:location.pathname===l.path?'#d6e1ff':'#a5b4ca',fontSize:12,p:.9,whiteSpace:'nowrap',bgcolor:location.pathname===l.path?'rgba(100,140,255,.16)':'transparent'}}>{l.label}</Button>)}</Box>
   <Box sx={{display:'flex',alignItems:'center',gap:1,ml:'auto',flexShrink:0}}><Chip label="SECURE" size="small" sx={{display:{xs:'none',lg:'flex'},color:'#71e8b5',bgcolor:'rgba(52,211,153,.1)'}}/>{me&&<Box sx={{display:'flex',alignItems:'center',gap:1}}><Avatar sx={{width:31,height:31,fontSize:12,bgcolor:'#304466'}}>{me.username?.[0]?.toUpperCase()||'?'}</Avatar><Typography sx={{display:{xs:'none',lg:'block'},fontSize:12}}>{me.username} · {me.role}</Typography></Box>}<IconButton aria-label="Sign out" onClick={signOut} sx={{color:'text.secondary'}}><LogoutOutlinedIcon/></IconButton></Box>
  </Toolbar></AppBar>
  <Drawer open={open} anchor="left" onClose={()=>setOpen(false)} PaperProps={{sx:{width:285,p:2,bgcolor:'#111c2d'}}}><Typography fontWeight={800} sx={{mb:2}}>SentinelVision</Typography><List>{links.map(l=><ListItemButton key={l.path} selected={location.pathname===l.path} onClick={()=>go(l.path)}><ListItemText primary={l.label}/></ListItemButton>)}<ListItemButton onClick={signOut}><LogoutOutlinedIcon sx={{mr:1.5}}/><ListItemText primary="Sign out"/></ListItemButton></List></Drawer>
 </>;
}
