// Iframe messages use the same JSON data contract as the backend. Vue-backed
// widget arrays can be Proxies, which postMessage cannot structured-clone.
export function messageData(value){return JSON.parse(JSON.stringify(value));}
