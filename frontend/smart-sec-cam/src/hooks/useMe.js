import React from 'react';
import { fetchMe } from '../api/systemApi';
// Permissions refresh while a session is open, including after a role change.
export default function useMe(token){
 const [me,setMe]=React.useState(null);
 React.useEffect(()=>{
  if(!token){setMe(null);return undefined;}
  let active=true;
  const refresh=()=>fetchMe(token).then(value=>{if(active)setMe(value.user);}).catch(()=>{if(active)setMe(null);});
  refresh();const id=setInterval(refresh,45000);window.addEventListener('focus',refresh);
  return()=>{active=false;clearInterval(id);window.removeEventListener('focus',refresh);};
 },[token]);return me;
}
