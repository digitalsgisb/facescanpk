import React, {useCallback, useEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {Bell, BellOff, LogIn, LogOut, X} from 'lucide-react';
import {createAttendanceTracker} from './attendance-events.js';
import './attendance-notifications.css';

const SOUND_KEY = 'attendance-notification-sound';
const timeLabel = value => new Intl.DateTimeFormat('en-MY', {timeZone:'Asia/Kuala_Lumpur', hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false}).format(new Date(value));

export function useAttendanceNotifications(snapshot, signedIn) {
  const tracker = useRef(createAttendanceTracker());
  const [queue, setQueue] = useState([]);
  const [sound, setSound] = useState(() => {try {return localStorage.getItem(SOUND_KEY) !== 'off';} catch {return true;}});
  const context = useRef(null), played = useRef(null);
  const unlock = useCallback(() => {
    try {
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (!Audio) return;
      if (!context.current || context.current.state === 'closed') context.current = new Audio();
      if (context.current.state === 'suspended') context.current.resume().catch(() => {});
    } catch { /* Visual notifications still work on browsers without audio. */ }
  }, []);
  useEffect(() => {
    if (!signedIn) {tracker.current = createAttendanceTracker(); setQueue([]); played.current = null; return;}
    if (snapshot) {
      const incoming = tracker.current(snapshot);
      if (incoming.length) setQueue(previous => [...previous, ...incoming]);
    }
  }, [snapshot, signedIn]);
  useEffect(() => {
    if (!sound) return;
    document.addEventListener('pointerdown', unlock);
    document.addEventListener('keydown', unlock);
    return () => {document.removeEventListener('pointerdown', unlock); document.removeEventListener('keydown', unlock);};
  }, [sound, unlock]);
  useEffect(() => () => {context.current?.close().catch(() => {});}, []);
  const current = queue[0];
  const dismiss = useCallback(() => setQueue(previous => previous.slice(1)), []);
  useEffect(() => {
    if (!current) return;
    const timer = setTimeout(dismiss, 3000);
    return () => clearTimeout(timer);
  }, [current, dismiss]);
  useEffect(() => {
    if (!current || played.current === current.id) return;
    played.current = current.id;
    const audio = context.current;
    if (!sound || audio?.state !== 'running') return;
    // A soft two-part bell, synthesized locally without an audio download.
    try {
      const start = audio.currentTime;
      [[1046.5, 0], [1568, .08]].forEach(([frequency, delay]) => {
        const oscillator = audio.createOscillator(), gain = audio.createGain();
        oscillator.type = 'sine'; oscillator.frequency.value = frequency;
        gain.gain.setValueAtTime(0, start + delay);
        gain.gain.linearRampToValueAtTime(.09, start + delay + .008);
        gain.gain.exponentialRampToValueAtTime(.0001, start + delay + .65);
        oscillator.connect(gain); gain.connect(audio.destination);
        oscillator.onended = () => {oscillator.disconnect(); gain.disconnect();};
        oscillator.start(start + delay); oscillator.stop(start + delay + .7);
      });
    } catch { /* Audio failure must never interrupt the attendance board. */ }
  }, [current, sound]);
  function toggleSound() {
    const enabled = !sound;
    setSound(enabled);
    try {localStorage.setItem(SOUND_KEY, enabled ? 'on' : 'off');} catch { /* Optional preference. */ }
    if (enabled) unlock();
  }
  return {current, dismiss, sound, toggleSound};
}

export function AttendanceSound({notifications}) {
  const {sound, toggleSound} = notifications;
  return <button className="secondary attendance-sound" onClick={toggleSound} aria-label={sound ? 'Mute attendance bell' : 'Enable attendance bell'} aria-pressed={sound} title={sound ? 'Attendance bell on · click to mute' : 'Attendance bell muted · click to enable'}>{sound ? <Bell size={17}/> : <BellOff size={17}/>}<span>Bell {sound ? 'on' : 'off'}</span></button>;
}

export function AttendanceNotifications({notifications}) {
  const [target, setTarget] = useState(() => document.fullscreenElement || document.body);
  useEffect(() => {
    const update = () => setTarget(document.fullscreenElement || document.body);
    document.addEventListener('fullscreenchange', update);
    return () => document.removeEventListener('fullscreenchange', update);
  }, []);
  const {current, dismiss} = notifications;
  return createPortal(<div className="attendance-notifications" role="status" aria-live="polite" aria-atomic="true">{current && <AttendanceNotice key={current.id} event={current} dismiss={dismiss}/>}</div>, target);
}

function AttendanceNotice({event, dismiss}) {
  const [broken, setBroken] = useState(false);
  const employee = event.employee, clockedIn = event.action === 'IN';
  const name = employee.nickname || employee.name || employee.id;
  const Icon = clockedIn ? LogIn : LogOut;
  return <article className={'attendance-notice ' + (clockedIn ? 'is-in' : 'is-out')}>
    <div className="attendance-notice-heading"><span><Bell size={15}/> LIVE ATTENDANCE</span><button onClick={dismiss} aria-label="Dismiss attendance notification"><X size={17}/></button></div>
    <div className="attendance-notice-person"><div className="attendance-notice-photo">{employee.photo_url && !broken ? <img src={employee.photo_url} alt="" onError={() => setBroken(true)}/> : name.split(' ').filter(Boolean).slice(0, 2).map(part => part[0]).join('')}</div><div><strong>{name}</strong><small>{[employee.department, employee.line].filter(Boolean).join(' · ') || employee.id}</small></div></div>
    <div className="attendance-notice-result"><span><Icon size={19}/>{clockedIn ? 'Clocked in' : 'Clocked out'}</span><time dateTime={event.occurred_at}>{timeLabel(event.occurred_at)} <small>MYT</small></time></div>
    <div className="attendance-notice-progress"/>
  </article>;
}
