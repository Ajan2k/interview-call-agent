import React, { useState, useRef, useEffect } from 'react';
import { UserAgent, UserAgentOptions, Registerer, Session, Invitation, Inviter, SessionState, RegistererState, Web } from 'sip.js';
import { Phone, PhoneOff, Activity, Terminal, X } from 'lucide-react';

export interface TeleforceAgentProps {
  autoDialNumber?: string;
  autoDialTriggerId?: string;
  candidateId?: string;
  candidateName?: string;
  candidateRole?: string;
  onCallEnded?: () => void;
}

export function TeleforceAgent({
  autoDialNumber,
  autoDialTriggerId,
  candidateId,
  candidateName,
  candidateRole,
  onCallEnded,
}: TeleforceAgentProps) {
  const [status, setStatus] = useState('Disconnected');
  const [session, setSession] = useState<Session | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [outboundNumber, setOutboundNumber] = useState('+91 ');
  const onCallEndedRef = useRef(onCallEnded);
  const candidateIdRef = useRef(candidateId);
  const candidateNameRef = useRef(candidateName);
  const candidateRoleRef = useRef(candidateRole);

  useEffect(() => {
    onCallEndedRef.current = onCallEnded;
  }, [onCallEnded]);

  useEffect(() => {
    candidateIdRef.current = candidateId;
    candidateNameRef.current = candidateName;
    candidateRoleRef.current = candidateRole;
  }, [candidateId, candidateName, candidateRole]);

  const safeOnCallEnded = () => {
    if (onCallEndedRef.current) onCallEndedRef.current();
  };

  const userAgentRef = useRef<UserAgent | null>(null);
  const registererRef = useRef<Registerer | null>(null);
  
  // Audio Context and WebSocket for AI Backend
  const audioContextRef = useRef<AudioContext | null>(null);
  const backendWsRef = useRef<WebSocket | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null);
  const aiDestinationRef = useRef<MediaStreamAudioDestinationNode | null>(null);
  const nextPlayTimeRef = useRef<number>(0);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);

  const addLog = (msg: string) => {
    console.log(msg);
    setLogs(prev => {
      const newLogs = [...prev, `${new Date().toLocaleTimeString()} - ${msg}`];
      return newLogs.length > 50 ? newLogs.slice(newLogs.length - 50) : newLogs;
    });
  };

  const initTeleforce = async () => {
    try {
      setStatus('Connecting to Teleforce...');
      addLog('Initializing SIP.js...');
      
      const uri = UserAgent.makeURI('sip:logeshai@platformsbc1.teleforce.cx');
      if (!uri) throw new Error("Failed to create URI");

      // Request microphone upfront during the user click. Not fatal if denied —
      // the AI replaces the local track with its own audio, so calls still work
      // via the silent-track fallback in mediaStreamFactory below.
      try {
        await navigator.mediaDevices.getUserMedia({ audio: true });
        addLog('Microphone permission granted upfront.');
      } catch (err: any) {
        addLog(`Mic permission denied (${err.message}). Continuing — AI calls use a silent local track.`);
      }

      // CRITICAL: Initialize AudioContext during user gesture so inbound calls can play audio
      if (!audioContextRef.current) {
        const ctx = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
        audioContextRef.current = ctx;
        if (ctx.state === 'suspended') {
           ctx.resume().catch(e => console.error(e));
        }
      }


      // Custom media factory: if the mic is blocked, fall back to a silent audio
      // track so incoming calls can still be accepted ("Permission denied" on
      // accept() was killing inbound calls). The AI's TTS audio replaces the
      // local track anyway, so the mic is never actually needed.
      const mediaStreamFactory = (constraints: MediaStreamConstraints): Promise<MediaStream> => {
        if (!constraints.audio && !constraints.video) {
          return Promise.resolve(new MediaStream());
        }
        return navigator.mediaDevices.getUserMedia(constraints).catch((err: any) => {
          addLog(`Mic unavailable (${err.message}) — answering with silent audio track.`);
          let ctx = audioContextRef.current;
          if (!ctx || ctx.state === 'closed') {
            ctx = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
            audioContextRef.current = ctx;
          }
          return ctx.createMediaStreamDestination().stream;
        });
      };

      const options: UserAgentOptions = {
        sessionDescriptionHandlerFactory: Web.defaultSessionDescriptionHandlerFactory(mediaStreamFactory),
        authorizationUsername: 'logeshai',
        authorizationPassword: 'Rr20cn5XcT',
        transportOptions: {
          server: 'wss://platformsbc1.teleforce.cx:9091/ws',
          keepAliveInterval: 15, // Send keep-alives every 15 seconds to prevent NAT timeouts
          keepAliveDebounce: 10,
        },
        uri: uri,
        logLevel: 'debug',
        delegate: {
          onInvite: (invitation) => {
            addLog("Incoming Call Received!");
            setStatus('Incoming Call... Auto answering');
            handleIncomingCall(invitation);
          }
        }
      };

      const ua = new UserAgent(options);
      userAgentRef.current = ua;

      addLog('Starting UserAgent...');
      await ua.start();
      
      const registerer = new Registerer(ua);
      registererRef.current = registerer;
      
      registerer.stateChange.addListener((newState) => {
        if (newState === RegistererState.Registered) {
          setStatus('Ready (Registered)');
          addLog(`Successfully registered as ${options.authorizationUsername}!`);
        } else if (newState === RegistererState.Unregistered) {
          setStatus('Registration Failed');
          addLog('Unregistered (Check SIP Domain/Credentials)');
        }
      });
      
      addLog('Sending SIP REGISTER...');
      await registerer.register();
    } catch (err: any) {
      addLog(`Connection Error: ${err.message}`);
      setStatus('Error connecting');
    }
  };

  // Start the audio bridge for a newly established call, recovering from a stale
  // WebSocket left behind by a previous call (which would otherwise silently skip
  // the bridge — the AI never receives 'start' and never speaks).
  const ensureAudioBridge = (s: Session) => {
    const existing = backendWsRef.current;
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      addLog('Bridge already active, ignoring duplicate Established event.');
      return;
    }
    if (existing) {
      addLog('Stale backend WebSocket found — resetting bridge.');
      try { existing.close(); } catch (e) {}
      backendWsRef.current = null;
    }
    setupAudioBridge(s);
  };

  const handleIncomingCall = async (invitation: Invitation) => {
    setSession(invitation);

    invitation.stateChange.addListener((newState) => {
      addLog(`Call State: ${newState}`);
      if (newState === SessionState.Established) {
        setStatus('Call Active (AI Listening)');
        addLog('Call Established. Starting Audio Bridge...');
        ensureAudioBridge(invitation);
      } else if (newState === SessionState.Terminated) {
        setStatus('Ready (Registered)');
        addLog('Call Terminated.');
        cleanupAudioBridge();
        setSession(null);
      }
    });

    try {
      addLog('Auto-answering call...');
      await invitation.accept({
        sessionDescriptionHandlerOptions: {
          constraints: { audio: true, video: false }
        }
      });
    } catch (e: any) {
      addLog(`Failed to accept call: ${e.message}`);
    }
  };

  const makeOutboundCall = async (numberToDial?: any) => {
    let passedNumber = typeof numberToDial === 'string' || typeof numberToDial === 'number' ? String(numberToDial) : undefined;
    const finalNumber = passedNumber || outboundNumber;
    
    if (!userAgentRef.current || !finalNumber) return;
    
    try {
      const cleanNumber = String(finalNumber).replace(/[\s\-()]/g, '');
      addLog(`Dialing ${cleanNumber}...`);
      setStatus('Dialing Outbound...');
      
      const target = UserAgent.makeURI(`sip:${cleanNumber}@platformsbc1.teleforce.cx`);
      if (!target) throw new Error(`Invalid target URI: sip:${cleanNumber}@platformsbc1.teleforce.cx`);

      const inviter = new Inviter(userAgentRef.current, target, {
        sessionDescriptionHandlerOptions: {
          constraints: { audio: true, video: false }
        }
      });
      
      inviter.delegate = {
        onBye: () => {
          addLog('Call ended by remote peer (BYE).');
          setStatus('Ready (Registered)');
          cleanupAudioBridge();
          setSession(null);
          safeOnCallEnded();
        }
      };
      
      setSession(inviter);

      inviter.stateChange.addListener((newState) => {
        if (newState === SessionState.Terminated) {
          setStatus('Ready (Registered)');
          addLog('Outbound Call Terminated.');
          cleanupAudioBridge();
          setSession(null);
          safeOnCallEnded();
        } else if (newState === SessionState.Established) {
          setStatus('Outbound Call Connected (AI Speaking)');
          addLog('Outbound Call Established!');
          ensureAudioBridge(inviter);
        }
      });

      await inviter.invite({
        requestDelegate: {
          onReject: (response) => {
            addLog(`SIP Rejected: ${response.message.statusCode} ${response.message.reasonPhrase}`);
            setStatus('Ready (Registered)');
            cleanupAudioBridge();
            setSession(null);
            safeOnCallEnded();
          }
        }
      });
    } catch (e: any) {
      addLog(`Dial Failed: ${e.message}`);
      setStatus('Ready (Registered)');
      setSession(null);
      safeOnCallEnded();
    }
  };

  console.log(`[TeleforceAgent-Render] autoDialNumber: ${autoDialNumber}, triggerId: ${autoDialTriggerId}, status: ${status}`);

  useEffect(() => {
    console.log(`[TeleforceAgent-Effect] Evaluating autoDialNumber: ${autoDialNumber}, status: ${status}`);
    if (autoDialNumber && status === 'Ready (Registered)') {
      console.log(`[TeleforceAgent-Effect] Triggering makeOutboundCall!`);
      if (session) {
        setSession(null); // Force clear previous stuck session
      }
      makeOutboundCall(autoDialNumber);
    }
  }, [autoDialNumber, autoDialTriggerId, status]);

  const setupAudioBridge = (currentSession: Session) => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = window.location.hostname || 'localhost';
    const wsUrl = `${wsProtocol}//${wsHost}:8000/api/voice/teleforce_stream`;
    const ws = new WebSocket(wsUrl);
    backendWsRef.current = ws;

    ws.onopen = () => {
      addLog('Python WebSocket Connected!');
      const isOutbound = currentSession instanceof Inviter;
      const mode = isOutbound ? 'outbound' : 'inbound';
      // The other party's number: caller ID for inbound, dialed number for outbound
      let phone = '';
      try {
        const remote = (currentSession as any).remoteIdentity;
        phone = remote?.uri?.user || remote?.displayName || '';
      } catch (e) {}
      addLog(`Initiating AI Session (Mode: ${mode}, Phone: ${phone || 'unknown'})`);
      ws.send(
        JSON.stringify({
          event: 'start',
          callMode: mode,
          phone,
          candidate_id: candidateIdRef.current || undefined,
          candidate_name: candidateNameRef.current || undefined,
          candidate_role: candidateRoleRef.current || undefined,
        })
      );
    };

    ws.onerror = () => {
      addLog('ERROR: Python WebSocket failed to connect!');
    };

    ws.onclose = () => {
      // Clear the ref so the next call can set up a fresh bridge
      if (backendWsRef.current === ws) {
        backendWsRef.current = null;
      }
    };

    ws.onmessage = async (event) => {
      if (typeof event.data === 'string') {
        const msg = JSON.parse(event.data);
        if (msg.event === 'media' && audioContextRef.current) {
          const base64Audio = msg.media.payload;
          playBase64Audio(base64Audio);
        } else if (msg.event === 'clear') {
          addLog('AI Barge-in: Stopping current playback...');
          activeSourcesRef.current.forEach(source => {
            try { source.stop(); } catch (e) {}
          });
          activeSourcesRef.current = [];
        } else if (msg.event === 'end_call') {
          addLog('AI ended the call. Hanging up...');
          try {
            if (currentSession.state === SessionState.Established) {
              currentSession.bye();
            }
          } catch (e: any) {
            addLog(`Hangup error: ${e.message}`);
          }
        }
      }
    };

    const pc = (currentSession.sessionDescriptionHandler as any).peerConnection as RTCPeerConnection;
    if (!pc) {
      addLog('No PeerConnection available.');
      return;
    }

    // Initialize Audio Context
    let audioCtx = audioContextRef.current;
    if (!audioCtx || audioCtx.state === 'closed') {
      audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
      audioContextRef.current = audioCtx;
    }
    // Auto-answered inbound calls have no user gesture — a suspended context here
    // means the AI's audio would be scheduled but never heard.
    if (audioCtx.state === 'suspended') {
      audioCtx.resume()
        .then(() => addLog('AudioContext resumed for call.'))
        .catch((e: any) => addLog(`AudioContext resume FAILED: ${e.message} — AI audio will be silent!`));
    }
    nextPlayTimeRef.current = audioCtx.currentTime;

    // Create a destination for AI audio to flow into the SIP call
    const destination = audioCtx.createMediaStreamDestination();
    aiDestinationRef.current = destination;

    // Replace the local microphone track with the AI audio track
    const aiTrack = destination.stream.getAudioTracks()[0];
    const sender = pc.getSenders().find(s => s.track && s.track.kind === 'audio');
    if (sender && aiTrack) {
      sender.replaceTrack(aiTrack).catch(err => addLog(`ReplaceTrack Error: ${err}`));
    }

    const remoteStream = new MediaStream();
    
    let processCount = 0;
    const connectStream = () => {
        if (remoteStream.getAudioTracks().length === 0) {
            addLog('connectStream: No audio tracks yet.');
            return;
        }
        if (processorRef.current) return; // already connected
        
        // Ensure audio context is running!
        if (audioCtx.state === 'suspended') {
            audioCtx.resume().then(() => addLog('AudioContext resumed!'));
        }
        
        addLog(`Connecting remote audio track... AudioCtx state: ${audioCtx.state}`);
        const source = audioCtx.createMediaStreamSource(remoteStream);
        const processor = audioCtx.createScriptProcessor(4096, 1, 1);
        processorRef.current = processor;
        
        processor.onaudioprocess = (e) => {
          processCount++;
          if (processCount === 1) addLog('onaudioprocess fired for the first time!');
          
          if (ws.readyState === WebSocket.OPEN) {
            const inputData = e.inputBuffer.getChannelData(0);
            const pcm16 = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
              let s = Math.max(-1, Math.min(1, inputData[i]));
              pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
    
            const buffer = new Uint8Array(pcm16.buffer);
            let binary = '';
            for (let i = 0; i < buffer.byteLength; i++) {
              binary += String.fromCharCode(buffer[i]);
            }
            const base64Audio = btoa(binary);
    
            ws.send(JSON.stringify({
              event: 'media',
              media: { payload: base64Audio }
            }));
          }
        };
        
        source.connect(processor);
        processor.connect(audioCtx.destination);
    };

    pc.getReceivers().forEach(receiver => {
      if (receiver.track) remoteStream.addTrack(receiver.track);
    });
    pc.ontrack = (event) => {
      if (event.track) {
          remoteStream.addTrack(event.track);
          connectStream();
      }
    };
    
    connectStream(); // Try to connect immediately if track already exists

    if (remoteAudioRef.current) {
      remoteAudioRef.current.srcObject = remoteStream;
      // MUST be unmuted for some browsers to process the audio graph!
      // We set volume to 0 instead so we don't hear echoing.
      remoteAudioRef.current.muted = false; 
      remoteAudioRef.current.volume = 0;
      remoteAudioRef.current.play().catch(e => addLog(`Play Error: ${e.message}`));
    }
    addLog('Audio bridge fully active.');
  };

  const playBase64Audio = async (base64: string) => {
    if (!audioContextRef.current) return;
    const ctx = audioContextRef.current;
    if (ctx.state === 'suspended') {
      ctx.resume().catch(() => {});
    }

    const binary = atob(base64);
    const len = binary.length;
    const buffer = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      buffer[i] = binary.charCodeAt(i);
    }
    const int16Array = new Int16Array(buffer.buffer);
    
    const audioBuffer = ctx.createBuffer(1, int16Array.length, 16000);
    const channelData = audioBuffer.getChannelData(0);
    for (let i = 0; i < int16Array.length; i++) {
      channelData[i] = int16Array[i] / 0x7FFF;
    }

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    
    // Connect to AI destination to send over the phone call
    if (aiDestinationRef.current) {
      source.connect(aiDestinationRef.current);
    }
    // Also connect to local speakers for debugging
    source.connect(ctx.destination);

    const playTime = Math.max(ctx.currentTime, nextPlayTimeRef.current);
    
    // Track active sources for barge-in
    activeSourcesRef.current.push(source);
    source.onended = () => {
      activeSourcesRef.current = activeSourcesRef.current.filter(s => s !== source);
    };

    source.start(playTime);
    nextPlayTimeRef.current = playTime + audioBuffer.duration;
  };

  const cleanupAudioBridge = () => {
    try {
      if (processorRef.current) {
        processorRef.current.disconnect();
      }
    } catch (e) {}
    processorRef.current = null;

    activeSourcesRef.current.forEach(source => {
      try { source.stop(); } catch (e) {}
    });
    activeSourcesRef.current = [];
    aiDestinationRef.current = null;

    // NOTE: Deliberately NOT closing the AudioContext. It was created during the
    // user's Connect click (user gesture) — closing it would force the next
    // auto-answered inbound call to create a new context with no gesture, which
    // Chrome leaves suspended, making the AI silent.

    try {
      if (backendWsRef.current) {
        backendWsRef.current.close();
      }
    } catch (e) {}
    backendWsRef.current = null;
  };

  const terminateCall = () => {
    if (session) {
      addLog('Hanging up manually...');
      try {
        if (session.state === SessionState.Established) {
          session.bye();
        } else if (session instanceof Inviter) {
          session.cancel();
        } else if (session instanceof Invitation) {
          session.reject();
        }
      } catch (e: any) {
        addLog(`Error terminating: ${e.message}`);
      }
      
      // Force cleanup locally to ensure UI unlocks
      setSession(null);
      setStatus('Ready (Registered)');
      cleanupAudioBridge();
      safeOnCallEnded();
    }
  };

  // State for popups
  const [activeModal, setActiveModal] = useState<'none' | 'dialer' | 'logs'>('none');

  // Keyboard support for dialing
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (activeModal !== 'dialer') return;
      if (e.key === 'Enter') {
        if (!session) {
          makeOutboundCall();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeModal, session]);

  
  

  // Keypad numbers
  const keypad = [
    { num: '1', letters: '' }, { num: '2', letters: 'ABC' }, { num: '3', letters: 'DEF' },
    { num: '4', letters: 'GHI' }, { num: '5', letters: 'JKL' }, { num: '6', letters: 'MNO' },
    { num: '7', letters: 'PQRS' }, { num: '8', letters: 'TUV' }, { num: '9', letters: 'WXYZ' },
    { num: '*', letters: '' }, { num: '0', letters: '+' }, { num: '#', letters: '' },
  ];

  const handleKeypadPress = (num: string) => {
    setOutboundNumber(prev => prev + num);
  };

  const [callDuration, setCallDuration] = useState(0);

  useEffect(() => {
    let interval: any = null;
    if (session) {
      interval = setInterval(() => {
        setCallDuration(prev => prev + 1);
      }, 1000);
    } else {
      setCallDuration(0);
    }
    return () => clearInterval(interval);
  }, [session]);

  const formatTimer = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = sec % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <>
      {/* App Icons placed in the Top Navigation */}
      <div className="flex items-center gap-2 px-2">
        {session && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-rose-50 border border-rose-200 text-rose-600 animate-pulse">
            <span className="w-2 h-2 rounded-full bg-rose-500"></span>
            <span className="text-xs font-mono font-bold">
              {candidateName ? `INTERVIEW: ${candidateName}` : 'LIVE'} ({formatTimer(callDuration)})
            </span>
          </div>
        )}

        <button 
          onClick={() => setActiveModal('dialer')}
          className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-50 hover:bg-indigo-100 border border-indigo-100 transition-colors group"
        >
          <Phone size={14} className="text-indigo-500 fill-indigo-100 group-hover:scale-105 transition-transform" />
          <span className="text-indigo-600 text-xs font-bold">Dialer</span>
        </button>

        <button 
          onClick={() => setActiveModal('logs')}
          className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-50 hover:bg-slate-100 border border-slate-200 transition-colors group"
        >
          <Terminal size={14} className="text-slate-500 group-hover:scale-105 transition-transform" />
          <span className="text-slate-600 text-xs font-bold">Logs</span>
        </button>
      </div>

      {/* DIALER MODAL */}
      {activeModal === 'dialer' && (
        <div className="fixed bottom-6 right-6 z-[9999]">
          <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-2xl w-[360px] flex flex-col items-center relative animate-in slide-in-from-bottom-8">
            
            <button 
              onClick={() => setActiveModal('none')}
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-600"
            >
              <X size={20} />
            </button>
            
            <h2 className="text-lg font-bold text-slate-800 mb-0.5">Phone Keypad</h2>
            <p className="text-[10px] text-slate-500 mb-3 bg-slate-100 px-2 py-0.5 rounded-full">{status}</p>

            {candidateName && (
              <div className="w-full bg-indigo-50/80 border border-indigo-100 rounded-lg px-3 py-2 mb-3 text-left">
                <div className="text-[9px] uppercase font-bold text-indigo-500 tracking-wider">Candidate Interview Target</div>
                <div className="text-xs font-bold text-indigo-950 truncate">{candidateName}</div>
                {candidateRole && <div className="text-[10px] text-indigo-700 font-medium truncate">{candidateRole}</div>}
              </div>
            )}

            <input 
              type="text" 
              value={outboundNumber}
              onChange={(e) => setOutboundNumber(e.target.value)}
              placeholder="+91 Enter phone number..." 
              className="w-full text-center text-xl font-bold tracking-wider text-slate-800 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 placeholder-slate-400 mb-3 h-10 px-3"
            />

            <div className="grid grid-cols-3 gap-x-4 gap-y-2 mb-4 w-full px-6">
              {keypad.map((key, i) => (
                <button 
                  key={i}
                  onClick={() => handleKeypadPress(key.num)}
                  className="w-full h-12 rounded-lg bg-slate-100 hover:bg-slate-200 flex flex-col items-center justify-center transition-colors active:bg-slate-300 shadow-sm border border-slate-200"
                >
                  <span className="text-lg font-medium text-slate-800 leading-none">{key.num}</span>
                  {key.letters && <span className="text-[8px] font-bold text-slate-500 tracking-widest mt-0.5">{key.letters}</span>}
                </button>
              ))}
            </div>

            {status === 'Disconnected' ? (
              <button 
                onClick={initTeleforce}
                className="w-full h-12 rounded-lg bg-blue-500 hover:bg-blue-600 flex items-center justify-center shadow-md transition-transform active:scale-[0.98]"
              >
                <div className="flex items-center gap-2 text-white font-medium"><Activity size={20} /> Connect Agent</div>
              </button>
            ) : session ? (
              <button 
                onClick={terminateCall}
                className="w-full h-12 rounded-lg bg-red-500 hover:bg-red-600 flex items-center justify-center shadow-md transition-transform active:scale-[0.98]"
              >
                <div className="flex items-center gap-2 text-white font-medium"><PhoneOff size={20} /> End Call</div>
              </button>
            ) : (
              <button 
                onClick={makeOutboundCall}
                className="w-full h-12 rounded-lg bg-green-500 hover:bg-green-600 flex items-center justify-center shadow-md transition-transform active:scale-[0.98]"
              >
                <div className="flex items-center gap-2 text-white font-medium"><Phone size={20} className="fill-white" /> Dial Number</div>
              </button>
            )}
            
          </div>
        </div>
      )}

      {/* LOGS MODAL (Old Teleforce Bridge UI) */}
      {activeModal === 'logs' && (
        <div className="fixed bottom-6 right-6 z-[9999]">
          <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-2xl w-[360px] flex flex-col gap-4 relative animate-in slide-in-from-bottom-8">
            
            <button 
              onClick={() => setActiveModal('none')}
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-600"
            >
              <X size={18} />
            </button>

            <div className="flex items-center justify-between mt-1">
              <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                <Activity size={18} className="text-blue-600" /> 
                Teleforce Bridge
              </h3>
              <span className="text-[10px] px-2 py-1 bg-gray-100 rounded-full font-bold">
                {status}
              </span>
            </div>
            
            <p className="text-xs text-gray-500">
              Leave this window open to receive calls. Currently mapped to account: <strong>logeshai</strong>.
            </p>

            {/* Terminal / Logs UI */}
            <div className="bg-slate-900 rounded-md p-3 h-48 overflow-y-auto flex flex-col justify-end">
              {logs.length === 0 ? (
                <p className="text-[10px] text-slate-500 font-mono italic">No logs yet. Click Connect.</p>
              ) : (
                logs.map((log, i) => (
                  <div key={i} className="flex gap-1.5 items-start text-[10px] font-mono text-green-400 mb-1 leading-tight">
                    <Terminal size={12} className="shrink-0 mt-0.5 text-slate-500" />
                    <span className="break-words flex-1">{log}</span>
                  </div>
                ))
              )}
            </div>

            {status === 'Disconnected' ? (
              <button 
                onClick={initTeleforce}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white py-2.5 rounded-md text-sm font-medium flex items-center justify-center gap-2 cursor-pointer transition shadow-sm"
              >
                <Phone size={16} /> Connect to logeshai
              </button>
            ) : (
              <div className="w-full bg-green-500/10 text-green-600 py-2.5 rounded-md text-sm font-bold flex items-center justify-center gap-2 border border-green-500/20">
                <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                Connected to Server
              </div>
            )}
          </div>
        </div>
      )}

      <audio ref={remoteAudioRef} style={{ display: 'none' }} autoPlay />
    </>
  );
}
