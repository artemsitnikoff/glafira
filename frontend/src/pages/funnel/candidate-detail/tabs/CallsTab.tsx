import { useState, useRef, useEffect } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useCalls } from '@/api/hooks/useCalls';
import { useCallSync, useCallSyncJobStatus, useTranscribeCall } from '@/api/mutations/callsMutations';
import { api } from '@/api/client';
import './CallsTab.css';

const CALL_WAVE = [8,14,22,31,19,12,26,38,44,30,18,11,24,40,52,46,33,21,14,28,42,55,48,36,24,16,30,46,58,50,38,26,18,12,22,36,48,40,28,17,11,20,33,44,30,19,12,9];

function fmtClock(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

interface CallPlayerProps {
  callId: string;
  durationSec: number;
  color?: string;
}

function CallPlayer({ callId, durationSec, color = 'var(--accent)' }: CallPlayerProps) {
  const [playing, setPlaying] = useState(false);
  const [pos, setPos] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);

  // Загрузка аудио лениво при первом play
  const loadAudio = async () => {
    if (audioUrl || loading) return;

    setLoading(true);
    setLoadError(false);
    try {
      const response = await api.get(`/calls/${callId}/recording`, { responseType: 'blob' });
      const url = URL.createObjectURL(response.data);
      setAudioUrl(url);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  };

  // Освобождаем blob-URL при размонтировании (иначе утечка памяти)
  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const updateTime = () => setPos(audio.currentTime);
    const handleEnded = () => setPlaying(false);

    audio.addEventListener('timeupdate', updateTime);
    audio.addEventListener('ended', handleEnded);

    return () => {
      audio.removeEventListener('timeupdate', updateTime);
      audio.removeEventListener('ended', handleEnded);
    };
  }, [audioUrl]);

  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.playbackRate = speed;
    }
  }, [speed]);

  const pct = Math.min(100, (pos / durationSec) * 100);

  const toggle = async () => {
    if (!audioUrl) {
      await loadAudio();
      return;
    }

    const audio = audioRef.current;
    if (!audio) return;

    if (playing) {
      audio.pause();
      setPlaying(false);
    } else {
      if (pos >= durationSec) {
        audio.currentTime = 0;
        setPos(0);
      }
      audio.play();
      setPlaying(true);
    }
  };

  const cycleSpeed = () => setSpeed(s => (s === 1 ? 1.5 : s === 1.5 ? 2 : 1));

  const seek = (e: React.MouseEvent) => {
    if (!trackRef.current || !audioRef.current) return;

    const r = trackRef.current.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    const newTime = ratio * durationSec;

    audioRef.current.currentTime = newTime;
    setPos(newTime);
  };

  const downloadRecording = async () => {
    if (!audioUrl) {
      await loadAudio();
    }

    if (audioUrl) {
      const a = document.createElement('a');
      a.href = audioUrl;
      a.download = `call_${callId}.mp3`;
      a.click();
    }
  };

  return (
    <div className="call-player" style={{'--cp-color': color} as React.CSSProperties}>
      {audioUrl && <audio ref={audioRef} src={audioUrl} />}

      <button
        className={`cp-play ${playing ? 'playing' : ''}`}
        onClick={toggle}
        disabled={loading}
        aria-label={playing ? 'Пауза' : 'Слушать'}
      >
        {loading ? (
          <Icon name="loader" size={14} />
        ) : playing ? (
          <Icon name="pause" size={14} />
        ) : (
          <Icon name="play" size={14} />
        )}
      </button>

      <div className="cp-wave" ref={trackRef} onClick={seek}>
        {CALL_WAVE.map((h, i) => {
          const barPct = (i / CALL_WAVE.length) * 100;
          return <span key={i} className={`cp-bar ${barPct <= pct ? 'on' : ''}`} style={{height: `${h}%`}}/>;
        })}
      </div>

      <span className="cp-time t-mono">
        {loadError ? 'запись недоступна' : `${fmtClock(pos)} / ${fmtClock(durationSec)}`}
      </span>

      <button className="cp-speed t-mono" onClick={cycleSpeed} title="Скорость воспроизведения">
        {speed}×
      </button>

      <button className="cp-dl icon-btn" onClick={downloadRecording} title="Скачать запись">
        <Icon name="download" size={15}/>
      </button>
    </div>
  );
}

interface CallsTabProps {
  candidateId: string;
  candidate: any;
}

export function CallsTab({ candidateId, candidate }: CallsTabProps) {
  const { data: calls = [], isLoading } = useCalls(candidateId);
  const callSyncMutation = useCallSync();
  const transcribeMutation = useTranscribeCall();
  const [syncJobId, setSyncJobId] = useState<string | null>(null);
  const syncJobQuery = useCallSyncJobStatus(syncJobId);
  const syncJob = syncJobQuery.data;

  useEffect(() => {
    // Остановить поллинг джоба когда он завершился
    if (syncJob && (syncJob.status === 'done' || syncJob.status === 'error')) {
      setTimeout(() => setSyncJobId(null), 3000);
    }
  }, [syncJob]);

  const handleSync = () => {
    // Ошибка запуска отражается в callSyncMutation.isError (баннер ниже)
    callSyncMutation.mutate(undefined, {
      onSuccess: (result) => setSyncJobId(result.job_id),
    });
  };

  const handleTranscribe = (callId: string) => {
    // Ошибка отражается в transcribeMutation.isError + статусе звонка при поллинге
    transcribeMutation.mutate(callId);
  };

  const answered = calls.filter(x => x.direction !== 'missed');
  const totalSec = answered.reduce((s, x) => s + x.duration_sec, 0);
  const missedCount = calls.filter(x => x.direction === 'missed').length;

  const dirMeta = {
    out: {
      label: 'Исходящий',
      cls: 'out',
    },
    in: {
      label: 'Входящий',
      cls: 'in',
    },
    missed: {
      label: 'Недозвон',
      cls: 'missed',
    },
  };

  const formatCallDate = (dateStr: string | null) => {
    if (!dateStr) return '';

    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
      return `сегодня · ${date.toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' })}`;
    } else if (diffDays === 1) {
      return `вчера · ${date.toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' })}`;
    } else {
      return `${date.toLocaleDateString('ru')} · ${date.toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' })}`;
    }
  };

  if (isLoading) {
    return (
      <div className="calls-tab">
        <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--fg-3)' }}>
          Загрузка звонков...
        </div>
      </div>
    );
  }

  return (
    <div className="calls-tab">
      {/* Summary strip */}
      <div className="calls-summary">
        <div className="calls-sum-left">
          <span className="calls-sum-item">
            <span className="calls-sum-num t-mono">{calls.length}</span> {calls.length === 1 ? 'звонок' : calls.length < 5 ? 'звонка' : 'звонков'}
          </span>
          <span className="calls-sum-sep"/>
          <span className="calls-sum-item">
            <span className="calls-sum-num t-mono">{fmtClock(totalSec)}</span> разговора
          </span>
          {missedCount > 0 && (
            <>
              <span className="calls-sum-sep"/>
              <span className="calls-sum-item calls-sum-missed">
                <span className="calls-sum-num t-mono">{missedCount}</span> недозвон{missedCount === 1 ? '' : missedCount < 5 ? 'а' : 'ов'}
              </span>
            </>
          )}
        </div>
        <div className="calls-mango" title="Телефония подключена через Манго Телеком">
          <span className="mango-dot"/>
          Манго Телеком{candidate?.phone ? ` · ${candidate.phone}` : ''}
        </div>
      </div>

      {/* Sync button */}
      <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'flex-end' }}>
        <button
          className="btn btn-sm btn-secondary"
          onClick={handleSync}
          disabled={callSyncMutation.isPending || (syncJob && syncJob.status === 'running')}
        >
          <Icon name="refresh" size={14} />
          {callSyncMutation.isPending || (syncJob && syncJob.status === 'running') ? 'Синхронизация...' : 'Синхронизировать звонки'}
        </button>
      </div>

      {/* Sync status */}
      {syncJob && (
        <div className="info-banner small" style={{ marginBottom: '16px' }}>
          <Icon name={syncJob.status === 'done' ? 'check' : syncJob.status === 'error' ? 'x' : 'loader'} size={14} />
          <div>
            {syncJob.status === 'running' && `Синхронизация... ${syncJob.matched || 0}/${syncJob.total || 0}`}
            {syncJob.status === 'done' && `Завершено: проверено ${syncJob.total}, создано ${syncJob.created}`}
            {syncJob.status === 'error' && `Ошибка: ${syncJob.error}`}
          </div>
        </div>
      )}

      {callSyncMutation.isError && !syncJob && (
        <div className="info-banner small" style={{ marginBottom: '16px' }}>
          <Icon name="x" size={14} />
          <div>Не удалось запустить синхронизацию. Проверьте подключение Манго в Настройках.</div>
        </div>
      )}

      {/* Call list */}
      {calls.length === 0 ? (
        <div className="call-empty-state">
          <Icon name="phone" size={24} style={{ color: 'var(--fg-4)' }} />
          <div className="call-empty-title">Звонков пока нет</div>
          <div className="call-empty-hint">
            Нажмите <strong>«Синхронизировать звонки»</strong>, чтобы загрузить историю из Манго
          </div>
        </div>
      ) : (
        <div className="calls-list">
          {calls.map(call => {
            const dm = dirMeta[call.direction];
            const missed = call.direction === 'missed';
            const canTranscribe = call.has_recording && call.transcribe_status === 'none';
            const isTranscribing = call.transcribe_status === 'running';

            return (
              <div key={call.id} className={`call-card ${missed ? 'missed' : ''}`}>
                <div className="call-head">
                  <span className={`call-dir call-dir-${dm.cls} ${missed ? 'call-dir-missed' : ''}`}>
                    {call.direction === 'out' && (
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M7 17 17 7"/><path d="M8 7h9v9"/>
                      </svg>
                    )}
                    {call.direction === 'in' && (
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M17 7 7 17"/><path d="M16 17H7V8"/>
                      </svg>
                    )}
                    {call.direction === 'missed' && (
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M7 17 17 7"/><path d="M8 7h9v9"/><line x1="2" y1="22" x2="22" y2="2" stroke="currentColor" strokeWidth="2"/>
                      </svg>
                    )}
                  </span>
                  <span className="call-title">
                    {call.direction === 'missed' ? 'Недозвон' : call.direction === 'in' ? 'Входящий звонок' : 'Исходящий звонок'}
                  </span>
                  {missed ? (
                    <span className="call-status call-status-missed">Не дозвонился</span>
                  ) : (
                    <span className="call-status call-status-ok">{dm.label} · {fmtClock(call.duration_sec)}</span>
                  )}
                  <span className="call-spacer"/>
                  {call.recruiter_name && (
                    <span className="call-recruiter">{call.recruiter_name}</span>
                  )}
                  <span className="call-when t-mono">{formatCallDate(call.started_at)}</span>
                </div>

                {!missed && call.has_recording && (
                  <CallPlayer
                    callId={call.id}
                    durationSec={call.duration_sec}
                    color={call.direction === 'in' ? '#16A34A' : 'var(--accent)'}
                  />
                )}

                {call.summary && (
                  <div className="call-summary">
                    <div className="call-block-label">
                      <span className="glafira-emoji">👩🏻</span> Краткое содержание
                    </div>
                    <div className="call-summary-text">{call.summary}</div>
                  </div>
                )}

                {call.ai_hint && call.ai_hint_tone && (
                  <div className={`call-hint call-hint-${call.ai_hint_tone}`}>
                    <div className="call-hint-mark">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.79.68-1.4 1.41-2a5 5 0 1 0-7 0c.73.6 1.23 1.21 1.41 2"/>
                      </svg>
                    </div>
                    <div className="call-hint-body">
                      <div className="call-hint-title">
                        {call.ai_hint_tone === 'good' ? 'AI-разбор звонка' : 'AI-подсказка: что улучшить'}
                      </div>
                      <div className="call-hint-text">{call.ai_hint}</div>
                    </div>
                  </div>
                )}

                {/* Расшифровка */}
                {call.has_recording && !call.transcript && (
                  <div style={{ marginTop: '12px' }}>
                    {isTranscribing ? (
                      <div className="call-transcribe-status">
                        <Icon name="loader" size={14} />
                        Глафира расшифровывает... 💃
                      </div>
                    ) : call.transcribe_status === 'error' ? (
                      <div className="call-transcribe-error">
                        <Icon name="x" size={14} />
                        Ошибка расшифровки: {call.transcribe_error}
                      </div>
                    ) : canTranscribe ? (
                      <button
                        className="btn btn-sm btn-secondary"
                        onClick={() => handleTranscribe(call.id)}
                        disabled={transcribeMutation.isPending}
                      >
                        <Icon name="brain" size={14} />
                        Расшифровать / Разбор
                      </button>
                    ) : null}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}