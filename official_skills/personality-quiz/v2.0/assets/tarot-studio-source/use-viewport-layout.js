import {useLayoutEffect, useRef, useState} from 'react';
import {tableLayout} from './viewport-layout';

function readSize() {
  const probe = document.getElementById('viewport-probe');
  const rect = probe.getBoundingClientRect(), style = getComputedStyle(probe);
  const left = parseFloat(style.paddingLeft), right = parseFloat(style.paddingRight);
  const top = parseFloat(style.paddingTop), bottom = parseFloat(style.paddingBottom);
  return {width:Math.floor(rect.width-left-right),height:Math.floor(rect.height-top-bottom),left,right,top,bottom};
}
export function useViewportLayout(busy, hasQuestion) {
  const [size, setSize] = useState(readSize);
  const busyRef = useRef(busy), pending = useRef(null);
  busyRef.current = busy;
  const commit = next => setSize(old => Object.keys(next).every(key=>old[key]===next[key]) ? old : next);
  useLayoutEffect(()=>{
    const probe=document.getElementById('viewport-probe');
    let frame=0;
    const observer=new ResizeObserver(()=>{
      cancelAnimationFrame(frame);
      frame=requestAnimationFrame(()=>{
        const next=readSize();
        if(busyRef.current)pending.current=next;
        else commit(next);
      });
    });
    observer.observe(probe);
    return()=>{observer.disconnect();cancelAnimationFrame(frame);};
  },[]);
  useLayoutEffect(()=>{
    if(!busy&&pending.current){commit(pending.current);pending.current=null;}
  },[busy]);
  // Memoize via the dimensions so selecting/revealing cards never changes geometry.
  const cache=useRef(null),key=JSON.stringify(size)+String(hasQuestion);
  if(cache.current?.key!==key)cache.current={key,value:tableLayout(size.width,size.height,hasQuestion)};
  return {...cache.current.value,insets:size};
}
