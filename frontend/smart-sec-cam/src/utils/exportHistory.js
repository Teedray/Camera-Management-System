// The current backend returns a direct MP4 stream, not an export job. These
// entries record this browser's requests only, never falsely imply cloud storage.
const KEY='sentinel-export-history-v1';
export function readExportHistory(){try{const raw=window.sessionStorage.getItem(KEY);return raw?JSON.parse(raw):[];}catch(e){return [];}}
export function writeExportHistory(entry){try{const old=readExportHistory();window.sessionStorage.setItem(KEY,JSON.stringify([entry,...old.filter(x=>x.id!==entry.id)].slice(0,25)));}catch(e){/* storage disabled */}}
