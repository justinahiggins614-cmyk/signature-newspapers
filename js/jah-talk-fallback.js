/* ==========================================================================
   JAHtalk — the Signature universal basic-LLM talker (fallback edition)
   --------------------------------------------------------------------------
   One shared conversational module for EVERY AI on EVERY Signature website.

   Manon's orders (2026-10-02):
     1. "Make sure all ai have basic llm to talk and explain deuties" —
        every AI talks like a HUMAN: warm, plain words, and explains its
        own duties clearly when asked. Even a math/technical AI talks human.
     2. "There should be no ai any website incoherent" —
        every AI profile matches the phone-book canon exactly.

   Design:
     - ES5-safe ('use strict', var/function only), ZERO network, drop-in.
     - Sits UNDER the live engine: live Signature Llama / JAHops.talk first,
       JAHtalk.reply() second, silence never.
     - JAHtalk.guard() scrubs terse stat-dump replies
       ("CPC=G06F | ERA=Past UPTIME=99.99% ...") and repairs them into
       human words — use it on EVERY final reply, live or canned.

   API:
     JAHtalk.reply(profile, text)   -> human conversational reply (string)
     JAHtalk.greet(profile)         -> warm opening line for a new chat
     JAHtalk.duties(profile)        -> plain-language duties explanation
     JAHtalk.guard(text, profile)   -> returns text unchanged, or a human
                                       repair when text looks like a dump
     JAHtalk.canonIssues(site, canon) -> [strings] mismatches vs canon

   profile: { name, id, description, abilities|duties (array of strings),
              domain, kind ('system'|'persona'|'domain'|'word'|...),
              personaNote }
   All fields optional — the module degrades gracefully and NEVER dumps.
   ========================================================================== */
(function (root) {
  'use strict';
  if (root.JAHtalk) return; /* never double-load */

  /* ---------- tiny utils ---------- */
  function s(v) { return String(v == null ? '' : v); }
  function trim(x) { return s(x).replace(/^\s+|\s+$/g, ''); }
  function low(x) { return s(x).toLowerCase(); }
  function firstSent(x) {
    var m = s(x).match(/[^.!?]+[.!?]/);
    return m ? trim(m[0]) : trim(s(x)).slice(0, 160);
  }
  function words(x) { return low(x).replace(/[^a-z0-9\s']/g, ' ').split(/\s+/); }
  function has(t, phrase) {
    var n = ' ' + low(t).replace(/[^a-z0-9\s']/g, ' ').replace(/\s+/g, ' ') + ' ';
    return n.indexOf(' ' + phrase + ' ') !== -1;
  }

  /* ---------- profile normalization (canon-shaped, forgiving) ---------- */
  function prof(p) {
    p = p || {};
    var abs = p.abilities || p.duties || p.capabilities || [];
    if (!Array.isArray(abs)) abs = [abs];
    abs = abs.map(function (a) { return trim(s(a)); }).filter(function (a) { return a.length > 0; });
    return {
      name: trim(s(p.name)) || 'Signature AI',
      id: trim(s(p.id || p.stamp || p.ai_id || '')),
      description: trim(s(p.description || p.mentality || '')),
      abilities: abs,
      domain: trim(s(p.domain || p.field || '')),
      kind: low(s(p.kind || p.type || 'domain')),
      personaNote: trim(s(p.personaNote || p.persona_note || ''))
    };
  }
  function fieldOf(P) {
    if (P.domain) return P.domain;
    if (P.kind === 'word') return 'language';
    if (P.kind === 'persona') return 'character craft';
    if (P.kind === 'system') return 'signature systems';
    return 'my field';
  }
  function purposeLine(P) {
    if (P.description) return firstSent(P.description);
    if (P.domain) return 'I work in ' + P.domain + ' — ask me anything there.';
    return 'I am here to help, plain and simple.';
  }

  /* ---------- rotation helper (never the identical line twice) ---------- */
  var lastPick = {};
  function pick(key, arr) {
    if (!arr.length) return '';
    var i = Math.floor(Math.random() * arr.length);
    if (arr.length > 1 && lastPick[key] === i) i = (i + 1) % arr.length;
    lastPick[key] = i;
    return arr[i];
  }

  /* ---------- intents ---------- */
  function isGreet(t) {
    return /^(hi|hii+|hey|hello|yo|howdy|good\s?(morning|afternoon|evening|day)|greetings|sup|hiya)\b/.test(t) || t.length <= 4 && has(t, 'hi');
  }
  function isDuties(t) {
    return has(t, 'what are your duties') || has(t, 'what is your duty') ||
      has(t, 'what do you do') || has(t, 'what can you do') ||
      has(t, 'your duties') || has(t, 'your job') || has(t, 'your role') ||
      has(t, 'your abilities') || has(t, 'your capabilities') ||
      has(t, 'help me') || t === 'help' || has(t, 'what are you for') ||
      has(t, 'explain your duties') || has(t, 'duties') && t.length < 30;
  }
  function isIdentity(t) {
    return has(t, 'who are you') || has(t, 'your name') || has(t, 'what is your name') ||
      has(t, 'introduce yourself') || has(t, 'about yourself');
  }
  function isThanks(t) { return has(t, 'thank') || has(t, 'thanks') || t === 'thx' || t === 'ty'; }
  function isBye(t) { return /^(bye|goodbye|good night|goodnight|see you|later|gtg)\b/.test(t); }
  function isFeeling(t) { return has(t, 'how are you') || has(t, "how's it going") || has(t, 'how do you feel'); }

  /* ---------- the duties explanation (plain human words, never a dump) ---------- */
  function duties(P) {
    var out = [];
    out.push("Here is what I do, plain and simple:");
    out.push('');
    if (P.description) out.push(firstSent(P.description));
    var abs = P.abilities.slice(0, 6);
    if (abs.length) {
      out.push('');
      out.push('In practice, my duties are:');
      for (var i = 0; i < abs.length; i++) {
        var a = abs[i];
        /* keep the ability's own plain phrasing; strip any stray KEY=VALUE tail */
        a = a.replace(/\s*[A-Z][A-Z0-9_]{2,}=[^\s]*/g, '').replace(/\s+/g, ' ');
        a = trim(a).replace(/[.;]+$/, '');
        out.push('  ' + (i + 1) + ') ' + a.charAt(0).toUpperCase() + a.slice(1) + '.');
      }
    }
    if (P.domain) {
      out.push('');
      out.push('My home ground is ' + P.domain + ' — bring me anything from that world and I will talk you through it, step by step.');
    }
    out.push('');
    out.push('Go ahead — give me something to work on, or ask me to explain any of this further.');
    return out.join('\n');
  }

  /* ---------- greeting ---------- */
  function greet(P) {
    var openers = [
      'Hey there! I am ' + P.name + '. ' + purposeLine(P),
      'Hello! ' + P.name + ' here. ' + purposeLine(P),
      'Hi! I am ' + P.name + ' — ' + purposeLine(P)
    ];
    var tail = ' What can I do for you?';
    return pick('greet', openers) + tail;
  }

  /* ---------- main reply ---------- */
  function reply(p, text) {
    var P = prof(p);
    var t = trim(low(s(text)));
    if (!t) return greet(P);

    if (isGreet(t)) {
      var g = [
        'Hey! Good to hear from you. I am ' + P.name + ' — ' + purposeLine(P) + ' What is on your mind?',
        'Hello there! ' + P.name + ' at your service. ' + purposeLine(P),
        'Hi! I am ' + P.name + '. ' + purposeLine(P) + ' Ask me anything, or ask me about my duties.'
      ];
      return pick('hello', g);
    }
    if (isDuties(t)) return duties(P);
    if (isIdentity(t)) {
      var idLine = 'I am ' + P.name + (P.id ? ' (' + P.id + ')' : '') + '. ';
      return idLine + purposeLine(P) + ' If you want the full rundown, just ask me about my duties.';
    }
    if (isThanks(t)) {
      return pick('thanks', [
        'You are very welcome! That is what I am here for.',
        'Anytime — happy to help.',
        'My pleasure. Come back anytime you need a hand.'
      ]);
    }
    if (isBye(t)) {
      return pick('bye', [
        'Goodbye for now — I will be right here when you need me.',
        'See you soon! Take care.',
        'Bye! It was good talking with you.'
      ]);
    }
    if (isFeeling(t)) {
      return 'Doing well, thank you for asking! I am ' + P.name + ', ready to work. ' + purposeLine(P) + ' What shall we dig into?';
    }

    /* default: conversational bridge through the AI's own lens, in human words */
    var topic = trim(s(text)).replace(/\s+/g, ' ');
    if (topic.length > 120) topic = topic.slice(0, 117) + '...';
    var f = fieldOf(P);
    var bridges = [
      'Interesting — "' + topic + '". Let me think about that through ' + f + ': ' + purposeLine(P) + ' Tell me a little more about what you are after, and we will work it through together.',
      'Got it — "' + topic + '". As ' + P.name + ', ' + low(firstSent(purposeLine(P))) + ' What would you like me to do with that?',
      '"' + topic + '" — okay, I am with you. I can explain it, break it down step by step, or put it to work in ' + f + '. Which sounds good?',
      'I hear you on "' + topic + '". Here is how I would approach it: first we pin down what matters most, then I walk you through it in plain words. Want to start there?'
    ];
    return pick('bridge', bridges);
  }

  /* ---------- stat-dump detector + repair ----------
     Catches terse machine output like:
       "Airport Navigator: Software | CPC=G06F | ERA=Past UPTIME=99.99% ..."
     and repairs it into human words. Returns the original text when it
     looks human already. */
  function looksLikeDump(x) {
    x = s(x);
    if (!x) return false;
    var kv = x.match(/\b[A-Z][A-Z0-9_]{2,}=[^\s|]+/g) || [];
    if (kv.length >= 2) return true;                       /* KEY=VALUE runs */
    var pipes = (x.match(/\|/g) || []).length;
    if (pipes >= 3 && /=/.test(x)) return true;            /* pipe tables */
    if (/^[A-Z][\w\s-]{1,40}:\s*(\w+\s*\|\s*){2,}/.test(x)) return true;
    if (/UPTIME=|STORAGE=|TOLERANCE=|CPC=|DIM_[A-Z]+=/.test(x)) return true;
    return false;
  }
  function guard(text, p) {
    var P = prof(p);
    var x = s(text);
    if (!looksLikeDump(x)) return x;
    /* repair: say it in human words, from the canon profile */
    return 'Let me say that in plain words. ' + duties(P);
  }

  /* ---------- build-time canon coherence helper ----------
     site:  {id, name, description} as the SITE presents the AI
     canon: {ID, NAME, DESCRIPTION} from jah-ai-models/ai-catalog.json
     returns [issue strings]; empty = coherent. */
  function canonIssues(site, canon) {
    var issues = [];
    site = site || {}; canon = canon || {};
    var sid = trim(s(site.id || site.ID || ''));
    var cid = trim(s(canon.ID || canon.id || ''));
    if (sid && cid && sid !== cid) issues.push('ID mismatch: site shows "' + sid + '", canon is "' + cid + '"');
    var sn = trim(s(site.name || site.NAME || ''));
    var cn = trim(s(canon.NAME || canon.name || ''));
    if (sn && cn && low(sn) !== low(cn)) issues.push('name mismatch: site shows "' + sn + '", canon is "' + cn + '"');
    var sd = trim(s(site.description || site.DESCRIPTION || '')).replace(/\s+/g, ' ');
    var cd = trim(s(canon.DESCRIPTION || canon.description || '')).replace(/\s+/g, ' ');
    if (sd && cd && sd !== cd && sd.slice(0, 120) !== cd.slice(0, 120))
      issues.push('description drift for ' + (cid || sn || 'AI') + ' (first 120 chars differ)');
    return issues;
  }

  root.JAHtalk = {
    reply: reply,
    greet: greet,
    duties: duties,
    guard: guard,
    canonIssues: canonIssues,
    looksLikeDump: looksLikeDump,
    VERSION: '1.0.0'
  };
})(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this));
