import { useState, useEffect } from 'react';
import { createClient } from '@supabase/supabase-js';
import './App.css';

const SUPABASE_URL = 'https://ajhxasizxhjkuuisvrjt.supabase.co';
const SUPABASE_KEY = 'sb_publishable_jJNTc0yPKEYWkO54nYUNZA_9cf6bUr7';
const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

const manifestoLines = [
  { text: "We help hero teams hire heroes", muted: true },
  { text: "", muted: false },
  { text: "AI handles the grunt work now.", muted: false },
  { text: "Only hero teams made of hero individuals win.", muted: false },
  { text: "", muted: false },
  { text: "> Hero teams run lean—every hire must be a force multiplier.", muted: false },
  { text: "> Heroes seek missions worth their time and allies worth their trust.", muted: false },
  { text: "", muted: false },
  { text: "Three questions separate heroes from the rest.", muted: false },
  { text: "Answer them. We help you find your kind.", muted: false },
  { text: "", muted: false },
  { text: "DIFFICULTY_PROMPT", muted: true, isSpecial: true }
];

const questions = [
  { key: 'grit', label: 'GRIT', question: 'Tell me about the hardest challenge you conquered.' },
  { key: 'badass', label: 'PEAK', question: "What accomplishment are you most proud of?" },
  { key: 'vision', label: 'VISION', question: "What's the future you strive to build for the next 5 years?" }
];

const PAGE_SIZE = 8;

function App() {
  const [user, setUser] = useState(null);
  const [step, setStep] = useState(1); // 1: questions, 2: dashboard
  const [activeTab, setActiveTab] = useState('recommendations'); // 'recommendations' or 'profile'
  const [lineIndex, setLineIndex] = useState(0);
  const [showCursor, setShowCursor] = useState(true);
  const [revealedInputs, setRevealedInputs] = useState(0);
  const [focusedInput, setFocusedInput] = useState(null);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [loading, setLoading] = useState(false);

  const [answers, setAnswers] = useState({ grit: '', badass: '', vision: '' });
  const [userType, setUserType] = useState(null); // 'hiring' or 'joining'
  const [selectedCharacters, setSelectedCharacters] = useState([]); // [{id, name}]
  const [preference, setPreference] = useState('');

  // Character list from DB
  const [characters, setCharacters] = useState([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [totalCount, setTotalCount] = useState(0);

  // Recommendations
  const [recommendations, setRecommendations] = useState([]);
  const [selectedProfile, setSelectedProfile] = useState(null);
  const [showPreferenceModal, setShowPreferenceModal] = useState(false);
  const [showDifficultyModal, setShowDifficultyModal] = useState(false);
  const [reminderEmail, setReminderEmail] = useState('');
  const [emailSubmitted, setEmailSubmitted] = useState(false);

  const wordCount = (text) => {
    return text?.trim() ? text.trim().split(/\s+/).length : 0;
  };

  const autoResize = (el) => {
    if (el) {
      el.style.height = 'auto';
      el.style.height = el.scrollHeight + 'px';
    }
  };

  const loadProfile = (profile) => {
    if (profile.answers) {
      setAnswers(profile.answers);
    }
    setUserType(profile.user_type || null);
    setSelectedCharacters(profile.selected_characters || []);
    setPreference(profile.preference || '');
  };

  const handlePendingSubmission = async (currentUser, fromSubmit = false) => {
    if (!currentUser) return;

    setLoading(true);
    setErrorMsg('');

    try {
      const { data: profiles, error } = await supabase
        .from('profiles')
        .select('*')
        .eq('user_id', currentUser.id);

      if (error) throw error;

      const dbProfile = profiles?.[0];

      if (dbProfile) {
        loadProfile(dbProfile);
        if (dbProfile.answers) {
          setStep(2);
          // If coming from submit, show profile tab; otherwise show recommendations
          setActiveTab(fromSubmit ? 'profile' : 'recommendations');
        }
      } else {
        const saved = localStorage.getItem('pendingSubmission');

        if (saved) {
          const pending = JSON.parse(saved);

          await supabase
            .from('profiles')
            .upsert({
              user_id: currentUser.id,
              answers: pending.answers,
              user_type: pending.user_type,
              updated_at: new Date().toISOString()
            }, { onConflict: 'user_id' });

          setAnswers(pending.answers);
          setUserType(pending.user_type);
          setStep(2);
          setActiveTab('profile'); // New user from submit, show profile
        }
      }
    } catch (e) {
      setErrorMsg("Error loading profile: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  // Fetch characters from DB
  const fetchCharacters = async (page = 0) => {
    const from = page * PAGE_SIZE;
    const to = from + PAGE_SIZE - 1;

    const { data, error, count } = await supabase
      .from('personality_character')
      .select('*', { count: 'exact' })
      .range(from, to)
      .order('name');

    if (!error && data) {
      setCharacters(data);
      setTotalCount(count || 0);
      setCurrentPage(page);
    }
  };

  // Fetch recommendations
  const fetchRecommendations = async () => {
    if (!user) return;

    const { data, error } = await supabase
      .from('profiles')
      .select('*')
      .neq('user_id', user.id)
      .not('answers', 'is', null)
      .limit(20);

    if (!error && data) {
      setRecommendations(data);
    }
  };

  // Typewriter effect for manifesto (only on step 1)
  useEffect(() => {
    if (step !== 1) return;

    if (lineIndex < manifestoLines.length) {
      const timer = setTimeout(() => {
        setLineIndex(prev => prev + 1);
      }, lineIndex === 0 ? 800 : 400);
      return () => clearTimeout(timer);
    } else if (lineIndex === manifestoLines.length && showCursor) {
      setShowCursor(false);
    }
  }, [lineIndex, showCursor, step]);

  // Reveal inputs after manifesto
  useEffect(() => {
    if (step !== 1) return;

    if (!showCursor && revealedInputs < 5) {
      const timer = setTimeout(() => {
        setRevealedInputs(prev => prev + 1);
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [showCursor, revealedInputs, step]);

  // Load data when entering step 2 (dashboard)
  useEffect(() => {
    if (step === 2) {
      if (activeTab === 'profile') {
        // No longer need to fetch characters here
      } else if (activeTab === 'recommendations') {
        fetchRecommendations();
        fetchCharacters(0);
        // Check if user has no preference info - auto show modal
        const hasPreferenceInfo = selectedCharacters.length > 0 || preference.trim();
        if (!hasPreferenceInfo) {
          setShowPreferenceModal(true);
        }
      }
    }
  }, [step, activeTab]);

  // Auth initialization
  useEffect(() => {
    const initAuth = async () => {
      const backupPending = localStorage.getItem('pendingSubmission');

      const hashParams = new URLSearchParams(window.location.hash.substring(1));
      const accessToken = hashParams.get('access_token');
      const refreshToken = hashParams.get('refresh_token');

      if (accessToken && refreshToken) {
        const { data, error } = await supabase.auth.setSession({
          access_token: accessToken,
          refresh_token: refreshToken
        });

        if (error) {
          setErrorMsg("Login failed: " + error.message);
        }

        if (data?.session) {
          setUser(data.session.user);

          if (backupPending && !localStorage.getItem('pendingSubmission')) {
            localStorage.setItem('pendingSubmission', backupPending);
          }

          window.history.replaceState({}, document.title, window.location.pathname);
          // From OAuth redirect, check if there was pending submission
          const hasPending = !!localStorage.getItem('pendingSubmission');
          await handlePendingSubmission(data.session.user, hasPending);
        }
      } else {
        const { data: { session } } = await supabase.auth.getSession();
        if (session) {
          setUser(session.user);
          await handlePendingSubmission(session.user, false);
        }
      }
    };

    initAuth();

    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (event === 'SIGNED_OUT') {
        setUser(null);
        setStep(1);
        return;
      }

      if (session && event === 'SIGNED_IN') {
        setUser(session.user);
        setShowLoginModal(false);
        const hasPending = !!localStorage.getItem('pendingSubmission');
        handlePendingSubmission(session.user, hasPending);
      }
    });

    return () => subscription?.unsubscribe();
  }, []);

  const validate = () => {
    for (const q of questions) {
      if (!answers[q.key]?.trim()) {
        return 'Please answer all questions.';
      }
      if (wordCount(answers[q.key]) > 140) {
        return 'Please keep each answer under 140 words.';
      }
    }
    if (!userType) {
      return 'Please select whether you want to hire or join.';
    }
    return null;
  };

  const submitAnswers = async () => {
    const err = validate();
    if (err) {
      setErrorMsg(err);
      return;
    }
    setErrorMsg('');

    const submission = {
      answers: { ...answers },
      user_type: userType
    };

    if (!user) {
      localStorage.setItem('pendingSubmission', JSON.stringify(submission));
      setShowLoginModal(true);
    } else {
      const { error } = await supabase
        .from('profiles')
        .upsert({
          user_id: user.id,
          answers: answers,
          user_type: userType,
          updated_at: new Date().toISOString()
        }, { onConflict: 'user_id' });

      if (error) {
        setErrorMsg("Failed to save: " + error.message);
        return;
      }

      setStep(2);
      setActiveTab('profile'); // From submit, show profile
    }
  };

  const loginWith = async (provider) => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider,
      options: { redirectTo: window.location.origin + window.location.pathname }
    });
    if (error) alert('Login failed: ' + error.message);
  };

  const logout = async () => {
    await supabase.auth.signOut();
    setUser(null);
    window.location.reload();
  };

  const toggleCharacter = (char) => {
    const exists = selectedCharacters.find(c => c.id === char.id);
    if (exists) {
      setSelectedCharacters(selectedCharacters.filter(c => c.id !== char.id));
    } else {
      setSelectedCharacters([...selectedCharacters, { id: char.id, name: char.name, image_url: char.image_url }]);
    }
  };

  const removeCharacter = (id) => {
    setSelectedCharacters(selectedCharacters.filter(c => c.id !== id));
  };

  const savePreferences = async () => {
    if (!user) {
      setErrorMsg('Please login first.');
      return;
    }

    const payload = {
      user_id: user.id,
      selected_characters: selectedCharacters,
      preference: preference,
      updated_at: new Date().toISOString()
    };

    const { error } = await supabase
      .from('profiles')
      .upsert(payload, { onConflict: 'user_id' });

    if (error) {
      setErrorMsg('Failed to save: ' + error.message);
      return;
    }

    setShowPreferenceModal(false);
    setErrorMsg('');
  };

  const saveProfile = async () => {
    if (!user) {
      setErrorMsg('Please login first.');
      return;
    }

    const payload = {
      user_id: user.id,
      answers: answers,
      user_type: userType,
      selected_characters: selectedCharacters,
      preference: preference,
      updated_at: new Date().toISOString()
    };

    const { error } = await supabase
      .from('profiles')
      .upsert(payload, { onConflict: 'user_id' });

    if (error) {
      setErrorMsg('Failed to save: ' + error.message);
      return;
    }

    window.location.reload();
  };

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);
  const displayedLines = manifestoLines.slice(0, lineIndex);

  const submitReminderEmail = async () => {
    if (!reminderEmail.trim() || !reminderEmail.includes('@')) {
      setErrorMsg('Please enter a valid email address.');
      return;
    }

    try {
      await supabase.from('reminder_emails').insert({
        email: reminderEmail.trim(),
        created_at: new Date().toISOString()
      });
      setEmailSubmitted(true);
      setErrorMsg('');
    } catch (e) {
      // If table doesn't exist, just show success anyway for now
      setEmailSubmitted(true);
      setErrorMsg('');
    }
  };

  return (
    <>
      <div className="screen-wrapper">
        {/* Header */}
        <div className="header">
          <div className="logo-container">
            <img src="/logo.svg" alt="hero4hero" className="logo" />
            <h1>hero for hero</h1>
          </div>
          <div className="user-status">
            {user ? (
              <>
                <span className="user-email">{user.email}</span>
                <button className="logout-btn" onClick={logout}>Logout</button>
              </>
            ) : (
              <button className="logout-btn" onClick={() => setShowLoginModal(true)}>Login</button>
            )}
          </div>
        </div>

        {loading && (
          <div className="manifesto-line" style={{ textAlign: 'center', marginBottom: '2rem' }}>
            &gt; ACCESSING ARCHIVES...
          </div>
        )}

        {/* Step 1: Questions */}
        {step === 1 && !loading && (
          <>
            {/* Manifesto */}
            <div className="manifesto">
              {displayedLines.map((line, i) => (
                line.isSpecial ? (
                  <div key={i} className="difficulty-prompt" onClick={() => setShowDifficultyModal(true)}>
                    <span>Feeling difficult answering these questions?</span>
                    <svg className="info-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10"/>
                      <path d="M12 16v-4M12 8h.01"/>
                    </svg>
                  </div>
                ) : (
                  <div key={i} className={`manifesto-line ${line.muted ? 'muted' : ''}`}>
                    {line.text || '\u00A0'}
                  </div>
                )
              ))}
              {showCursor && <span className="cursor"></span>}
            </div>

            {questions.map((q, i) => (
              <div key={q.key} className={`input-group ${revealedInputs > i ? 'revealed' : ''}`}>
                <div className="input-header">
                  <label className="input-label">{q.label}</label>
                  <span className="input-question">{q.question}</span>
                </div>
                <textarea
                  className="terminal-input"
                  value={answers[q.key]}
                  placeholder={focusedInput === q.key && !answers[q.key] ? '140 words max' : ''}
                  onFocus={() => setFocusedInput(q.key)}
                  onBlur={() => setFocusedInput(null)}
                  onChange={(e) => {
                    setAnswers({ ...answers, [q.key]: e.target.value });
                    autoResize(e.target);
                  }}
                  spellCheck="false"
                  maxLength={1000}
                />
                <div className="input-footer">
                  <span></span>
                  {answers[q.key] && (
                    <span className={`word-count ${wordCount(answers[q.key]) > 140 ? 'over' : ''}`}>
                      {wordCount(answers[q.key])} / 140 words
                    </span>
                  )}
                </div>
              </div>
            ))}

            <div className={`checkbox-container ${revealedInputs > 3 ? 'revealed' : ''}`}>
              <label className="checkbox-label" onClick={() => setUserType(userType === 'hiring' ? null : 'hiring')}>
                <span className={`checkbox-box ${userType === 'hiring' ? 'checked' : ''}`}></span>
                I'm assembling a hero crew
              </label>
              <label className="checkbox-label" onClick={() => setUserType(userType === 'joining' ? null : 'joining')}>
                <span className={`checkbox-box ${userType === 'joining' ? 'checked' : ''}`}></span>
                I'm looking for a hero team
              </label>
            </div>

            <div className={`btn-container ${revealedInputs > 4 ? 'revealed' : ''}`}>
              <button className="execute-btn" onClick={submitAnswers}>Submit</button>
              {errorMsg && <div className="error-msg">{errorMsg}</div>}
            </div>
          </>
        )}

        {/* Step 2: Dashboard */}
        {step === 2 && !loading && (
          <>
            {/* Tabs */}
            <div className="tabs">
              <button
                className={`tab ${activeTab === 'recommendations' ? 'active' : ''}`}
                onClick={() => setActiveTab('recommendations')}
              >
                Recommendations
              </button>
              <button
                className={`tab ${activeTab === 'profile' ? 'active' : ''}`}
                onClick={() => setActiveTab('profile')}
              >
                My Profile
              </button>
            </div>

            {/* Recommendations Tab */}
            {activeTab === 'recommendations' && (
              <>
                {/* Preference Summary */}
                {(selectedCharacters.length > 0 || preference.trim()) && (
                  <div className="preference-summary">
                    <div className="preference-summary-header">
                      <span className="preference-summary-title">YOUR PREFERENCES</span>
                      <button className="edit-preference-btn" onClick={() => setShowPreferenceModal(true)}>
                        Edit
                      </button>
                    </div>
                    <div className="preference-summary-content">
                      {selectedCharacters.length > 0 && (
                        <div className="preference-summary-heroes">
                          <span className="preference-label">Heroes:</span>
                          <div className="preference-heroes-grid">
                            {selectedCharacters.map(c => (
                              <div key={c.id} className="preference-hero-card">
                                {c.image_url ? (
                                  <img src={c.image_url} alt={c.name} className="preference-hero-avatar" />
                                ) : (
                                  <div className="preference-hero-placeholder">{c.name.charAt(0)}</div>
                                )}
                                <span className="preference-hero-name">{c.name}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      {preference.trim() && (
                        <div className="preference-summary-text">
                          <span className="preference-label">Looking for:</span>
                          <span className="preference-value">{preference}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* No preferences yet - show prompt */}
                {!selectedCharacters.length && !preference.trim() && (
                  <div className="no-preference-prompt">
                    <span>Help us find better heroes for you</span>
                    <button className="edit-preference-btn" onClick={() => setShowPreferenceModal(true)}>
                      Set Preferences
                    </button>
                  </div>
                )}

                <div className="section-title">HEROES FOR YOU</div>
                <div className="section-subtitle">
                  Click on a hero to view their profile
                </div>

                {recommendations.length === 0 ? (
                  <div className="empty-state">We do founder-level screening to make sure you only see the best. Come back soon.</div>
                ) : (
                  <div className="recommendations-grid">
                    {recommendations.map(profile => (
                      <div
                        key={profile.user_id}
                        className="recommendation-card"
                        onClick={() => setSelectedProfile(profile)}
                      >
                        <div className="recommendation-avatar">
                          {profile.email?.charAt(0).toUpperCase() || '?'}
                        </div>
                        <div className="recommendation-info">
                          <div className="recommendation-badges">
                            {profile.user_type === 'hiring' && <span className="badge hiring">Hiring</span>}
                            {profile.user_type === 'joining' && <span className="badge searching">Looking</span>}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}

            {/* Profile Tab */}
            {activeTab === 'profile' && (
              <>
                {/* User's answers - editable */}
                <div className="section-title">YOUR ANSWERS TO THE CRITICAL QUESTIONS</div>
                {questions.map((q) => (
                  <div key={q.key} className="input-group revealed">
                    <div className="input-header">
                      <label className="input-label">{q.label}</label>
                      <span className="input-question">{q.question}</span>
                    </div>
                    <textarea
                      className="terminal-input"
                      value={answers[q.key]}
                      onChange={(e) => {
                        setAnswers({ ...answers, [q.key]: e.target.value });
                      }}
                      spellCheck="false"
                      maxLength={1000}
                    />
                    <div className="input-footer">
                      <span></span>
                      {answers[q.key] && (
                        <span className={`word-count ${wordCount(answers[q.key]) > 140 ? 'over' : ''}`}>
                          {wordCount(answers[q.key])} / 140 words
                        </span>
                      )}
                    </div>
                  </div>
                ))}

                <div className="btn-container revealed" style={{ marginTop: '2rem' }}>
                  <button className="execute-btn" onClick={saveProfile}>Save Profile</button>
                  {errorMsg && <div className="error-msg">{errorMsg}</div>}
                </div>
              </>
            )}
          </>
        )}
      </div>

      <div className="footer-status">SYSTEM: READY</div>

      {/* Login Modal */}
      {showLoginModal && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setShowLoginModal(false)}>
          <div className="modal-content">
            <div className="login-title">&gt; AUTHENTICATE TO CONTINUE</div>
            <div className="login-buttons">
              <button className="login-btn" onClick={() => loginWith('google')}>
                <svg viewBox="0 0 24 24">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                Continue with Google
              </button>
              <button className="login-btn" onClick={() => loginWith('github')}>
                <svg viewBox="0 0 24 24">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                </svg>
                Continue with GitHub
              </button>
              <button className="login-btn" onClick={() => loginWith('twitter')}>
                <svg viewBox="0 0 24 24">
                  <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                </svg>
                Continue with X
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Profile Detail Modal */}
      {selectedProfile && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setSelectedProfile(null)}>
          <div className="modal-content profile-modal">
            <button className="modal-close" onClick={() => setSelectedProfile(null)}>×</button>

            <div className="profile-header">
              <div className="profile-avatar">
                {selectedProfile.email?.charAt(0).toUpperCase() || '?'}
              </div>
              <div className="profile-badges">
                {selectedProfile.user_type === 'hiring' && <span className="badge hiring">Hiring</span>}
                {selectedProfile.user_type === 'joining' && <span className="badge searching">Looking for team</span>}
              </div>
            </div>

            {selectedProfile.answers && (
              <div className="profile-answers">
                {questions.map(q => (
                  <div key={q.key} className="profile-answer">
                    <div className="profile-answer-label">{q.label}</div>
                    <div className="profile-answer-text">
                      {selectedProfile.answers[q.key] || 'Not answered'}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {selectedProfile.preference && (
              <div className="profile-preference">
                <div className="profile-answer-label">LOOKING FOR</div>
                <div className="profile-answer-text">{selectedProfile.preference}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Difficulty Explanation Modal */}
      {showDifficultyModal && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setShowDifficultyModal(false)}>
          <div className="modal-content difficulty-modal">
            <button className="modal-close" onClick={() => setShowDifficultyModal(false)}>×</button>

            <div className="difficulty-modal-content">
              <p>I totally understand.</p>

              <p>My name is Wei. I've been on both sides—sweating through these questions, and asking them when hiring for my startup.</p>

              <p>They're hard because they matter. Skills fade. Titles are noise. But <strong>grit, vision, and the awesome things you've actually built</strong>—those tell the real story.</p>

              <p>Can't answer yet? That's not failure. <strong>That's a sign you have work to do.</strong></p>

              <p className="highlight-text">Go build something you think is awesome. Keep hacking and failing at it until you conquer it.</p>

              <p>Drop your email—I'll check in.</p>

              {!emailSubmitted ? (
                <div className="reminder-email-section">
                  <input
                    type="email"
                    className="reminder-email-input"
                    placeholder="your@email.com"
                    value={reminderEmail}
                    onChange={(e) => setReminderEmail(e.target.value)}
                  />
                  <button className="reminder-submit-btn" onClick={submitReminderEmail}>
                    Check in after 3 months
                  </button>
                </div>
              ) : (
                <div className="email-submitted-msg">
                  ✓ Got it! I'll reach out in 3 months. Now go build something amazing.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Preference Modal */}
      {showPreferenceModal && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setShowPreferenceModal(false)}>
          <div className="modal-content preference-modal">
            <button className="modal-close" onClick={() => setShowPreferenceModal(false)}>×</button>

            <div className="section-title">SELECT YOUR HEROES</div>
            <div className="section-subtitle">
              Help us find the best heroes for you by selecting characters you resonate with
            </div>

            <div className="character-grid">
              {characters.map(char => (
                <div
                  key={char.id}
                  className={`character-card ${selectedCharacters.find(c => c.id === char.id) ? 'selected' : ''}`}
                  onClick={() => toggleCharacter(char)}
                >
                  {char.image_url ? (
                    <img src={char.image_url} alt={char.name} className="character-image" />
                  ) : (
                    <div className="character-placeholder">{char.name.charAt(0)}</div>
                  )}
                  <div className="character-name">{char.name}</div>
                </div>
              ))}
            </div>

            {totalPages > 1 && (
              <div className="pagination">
                <button
                  className="page-btn"
                  disabled={currentPage === 0}
                  onClick={() => fetchCharacters(currentPage - 1)}
                >
                  Prev
                </button>
                <span className="page-info">{currentPage + 1} / {totalPages}</span>
                <button
                  className="page-btn"
                  disabled={currentPage >= totalPages - 1}
                  onClick={() => fetchCharacters(currentPage + 1)}
                >
                  Next
                </button>
              </div>
            )}

            {selectedCharacters.length > 0 && (
              <div className="selected-characters">
                <div className="section-subtitle">
                  Selected ({selectedCharacters.length})
                </div>
                <div className="selected-list">
                  {selectedCharacters.map(char => (
                    <div
                      key={char.id}
                      className="selected-chip"
                      onClick={() => removeCharacter(char.id)}
                    >
                      {char.name}
                      <span className="remove">×</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="preference-section">
              <div className="section-title">YOUR IDEAL COLLABORATOR</div>
              <div className="section-subtitle">Describe the type of person you're looking for</div>
              <textarea
                className="preference-input"
                value={preference}
                onChange={(e) => setPreference(e.target.value)}
                placeholder="e.g., Someone who ships fast and iterates..."
                spellCheck="false"
              />
            </div>

            <div className="modal-actions">
              <button className="execute-btn" onClick={savePreferences}>Save Preferences</button>
              {errorMsg && <div className="error-msg">{errorMsg}</div>}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default App;
