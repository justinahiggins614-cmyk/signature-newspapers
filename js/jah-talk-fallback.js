/* ==========================================================================
   JAHtalk — the Signature universal basic-LLM talker (GuideTalk engine v2.1)
   --------------------------------------------------------------------------
   One shared conversational module for EVERY AI on EVERY Signature website.

   Manon's orders:
     2026-10-02: "Make sure all ai have basic llm to talk and explain
       deuties" — every AI talks like a HUMAN: warm, plain words, and
       explains its own duties clearly when asked. Even a math/technical AI
       talks human. "There should be no ai any website incoherent" — every
       AI profile matches the phone-book canon exactly.
     2026-10-04: the conversational upgrade — no more "word blocks". Every
       reply is natural, flowing conversation: genuinely responsive to what
       the user actually asked, covering everything the AI can do, and able
       to chat about the whole JAH ecosystem (all 31 sites, what each does,
       its tabs and options) as context. Never word salad, never generic
       filler, never Mad-Libs templates.
     2026-10-04: v2.1 chat context — every AI keeps conversation memory
       (last 10 turns, entities mentioned, last numbered list, current
       topic) so follow-ups like "tell me more about it", "the second one"
       and "how do I download it?" resolve against what was just discussed.
       JAHtalk.chat()/chatFor() sessions; transcript persists to
       localStorage namespaced per AI (24h) where available.

   Design:
     - ES5-safe ('use strict', var/function only), ZERO network, drop-in.
     - Sits UNDER the live engine: live Signature Llama / JAHops.talk first,
       JAHtalk.reply() second, silence never.
     - The ecosystem KB (JAHtalk.ECO) is baked in so site talk works fully
       offline on every site that loads this file.
     - JAHtalk.guard() scrubs terse stat-dump replies
       ("CPC=G06F | ERA=Past UPTIME=99.99% ...") and repairs them into
       human words — use it on EVERY final reply, live or canned.
     - v2.1 chat sessions: JAHtalk.chatFor(profile, key) at each chat
       send-point gives the AI conversation memory (pronouns, ordinals,
       "tell me more", topic carryover). Replies stay in the AI's voice.

   API:
     JAHtalk.reply(profile, text[, chatOrKey]) -> human conversational reply
       (third arg optional: a ChatSession, or a chatFor key string, to ask
       with full conversation memory; omitted = stateless, exactly v2.0)
     JAHtalk.chat(profile[, chatId]) -> stateful chat session with memory
     JAHtalk.chatFor(profile, key)   -> cached session for one AI/surface
       (canon profile refreshed on every call, transcript memory kept)
       session.reply(text)  -> ask with conversation memory
       session.transcript() -> last 10 turns [{role, text}]
       session.topic()      -> current topic label (pronoun/ordinal target)
       session.reset()      -> clear memory (also clears localStorage)
     JAHtalk.greet(profile)         -> warm opening line for a new chat
     JAHtalk.duties(profile)        -> plain-language duties explanation
     JAHtalk.guard(text, profile)   -> returns text unchanged, or a human
                                       repair when text looks like a dump
     JAHtalk.canonIssues(site, canon) -> [strings] mismatches vs canon
     JAHtalk.findSite(q)            -> ecosystem site object or null
     JAHtalk.ecosystem()            -> the 31-site knowledge array

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
  function hashStr(x) {
    var h = 5381, i;
    x = s(x);
    for (i = 0; i < x.length; i++) h = ((h << 5) + h + x.charCodeAt(i)) & 0xffffffff;
    return h >>> 0;
  }
  /* deterministic variety: same input -> same phrasing, different input -> varied */
  function pickH(key, arr, salt) {
    if (!arr.length) return '';
    return arr[hashStr(key + '|' + s(salt)) % arr.length];
  }
  /* random variety that never repeats the identical line twice in a row */
  var lastPick = {};
  function pickR(key, arr) {
    if (!arr.length) return '';
    var i = Math.floor(Math.random() * arr.length);
    if (arr.length > 1 && lastPick[key] === i) i = (i + 1) % arr.length;
    lastPick[key] = i;
    return arr[i];
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
  function cleanAbility(a) {
    a = s(a).replace(/\s*[A-Z][A-Z0-9_]{2,}=[^\s]*/g, '').replace(/\s+/g, ' ');
    a = trim(a).replace(/[.;]+$/, '');
    return a.charAt(0).toUpperCase() + a.slice(1);
  }
  function purposeLine(P) {
    if (P.description) return firstSent(P.description);
    if (P.domain) return 'I work in ' + P.domain + ' — ask me anything there.';
    return 'I am here to help, plain and simple.';
  }
  /* one or two abilities, phrased as what the AI actually offers the user */
  function offerLine(P, t) {
    var abs = P.abilities.slice(0, 6);
    if (!abs.length) return 'answering your questions in plain words';
    var tw = words(t), best = null, bestScore = 0, i, j;
    for (i = 0; i < abs.length; i++) {
      var aw = words(abs[i]), score = 0;
      for (j = 0; j < tw.length; j++) if (tw[j].length > 3 && aw.indexOf(tw[j]) >= 0) score++;
      if (score > bestScore) { bestScore = score; best = abs[i]; }
    }
    if (best && bestScore > 0) return low(cleanAbility(best)).replace(/\.$/, '');
    if (abs.length === 1) return low(cleanAbility(abs[0])).replace(/\.$/, '');
    return low(cleanAbility(abs[0])).replace(/\.$/, '') + ' and ' +
           low(cleanAbility(abs[1])).replace(/\.$/, '');
  }
  function dutiesSummary(P) {
    var abs = P.abilities.slice(0, 3).map(function (a) { return low(cleanAbility(a)).replace(/\.$/, ''); });
    if (!abs.length) return 'chatting and answering questions';
    if (abs.length === 1) return abs[0];
    return abs.slice(0, -1).join(', ') + ' and ' + abs[abs.length - 1];
  }

  /* ---------- the JAH ecosystem knowledge base (all 31 sites) ----------
     Baked in: site talk works fully offline on every site loading this file.
     code/build_versions.py extracts the JSON between the ECO-JSON markers
     into data/ecosystem.json for the downloadable Python packages. */
  var ECO = /*ECO-JSON-START*/[
    {"n":1,"repo":"signature-math","url":"https://justinahiggins614-cmyk.github.io/signature-math/","name":"Signature Math","blurb":"his deterministic math grid foundation — the math everything else in the network is built on.","tabs":["Math Grid","Proofs","Signature Mark"],"aliases":["math","math grid"]},
    {"n":2,"repo":"jah-calculator","url":"https://justinahiggins614-cmyk.github.io/jah-calculator/","name":"Signature Universal Paradox Immune Calculator","blurb":"a safe hand-written calculator with paradox checking, project simulation and a lab — no eval, real answers.","tabs":["Basic","Scientific","Ask Anything","Paradox Check","Project","Simulate","Lab"],"aliases":["calculator","paradox calculator"]},
    {"n":3,"repo":"jah-dictionary","url":"https://justinahiggins614-cmyk.github.io/jah-dictionary/","name":"The Signature Dictionary","blurb":"255,611 entries of original definitions with a personal AI teacher, read-aloud, copy and download.","tabs":["Search","A–Z","Word AI","1 Million Archive"],"aliases":["dictionary"]},
    {"n":4,"repo":"jah-wiki","url":"https://justinahiggins614-cmyk.github.io/jah-wiki/","name":"JAH Wiki","blurb":"the Wikipedia-like encyclopedia over ALL the network's data — articles with analysis lenses, demos and working code.","tabs":["Search","Random Article","A–Z","Article Pages"],"aliases":["wiki","jah wiki","encyclopedia"]},
    {"n":5,"repo":"jah-n-wiki-leaks","url":"https://justinahiggins614-cmyk.github.io/jah-n-wiki-leaks/","name":"JAH-N Wiki","blurb":"the classified-dossier archive — every spec and patent as a signed-off dossier, marching to a million files.","tabs":["Dossiers","Search","AI Disc","Thumbdrive"],"aliases":["jah-n","wiki leaks","leaks","dossier","dossiers"]},
    {"n":6,"repo":"signature-llama","url":"https://justinahiggins614-cmyk.github.io/signature-llama/","name":"Signature Llama","blurb":"the fully cyber utilizable AI — this site: chat, four downloadable versions, a compiler and the archive.","tabs":["Main","Versions","Compiler","1 Million Archive","Best of the Best"],"aliases":["llama","signature llama","this site","here"]},
    {"n":7,"repo":"jah-ai-models","url":"https://justinahiggins614-cmyk.github.io/jah-ai-models/","name":"The Signature AI Phone Book","blurb":"the Yellow Pages of AI — dial any AI by number, three-way calling, 243 domain AIs and a million hybrids.","tabs":["Dial Pad","A–Z Directory","Mix Lab","Persona Archive"],"aliases":["phone book","telephone book","ai phone","yellow pages","dial"]},
    {"n":8,"repo":"cyber-patent-catalog","url":"https://justinahiggins614-cmyk.github.io/cyber-patent-catalog/","name":"Globally Rejustered Patent Catalog","blurb":"real harvested public patent records, every 30 minutes, full records listed and searchable.","tabs":["Search","Filter Pills","Patent Records"],"aliases":["patent catalog","patents","public patents"]},
    {"n":9,"repo":"signature-one-archive","url":"https://justinahiggins614-cmyk.github.io/signature-one-archive/specs.html","name":"Signature Spec Catalog Pending Patents","blurb":"his own original draft specs marching to a million — 24 group cards, lens tabs and an academy.","tabs":["Group Cards","Spec Lenses","Academy","Search"],"aliases":["spec catalog","specs","spec archive","pending patents"]},
    {"n":10,"repo":"jah-computer-systems","url":"https://justinahiggins614-cmyk.github.io/jah-computer-systems/","name":"The Signature PC System Depository","blurb":"every computer system from historic to predicted, marching to a million PCs, each with demos.","tabs":["Categories","System Files","Simulators"],"aliases":["pc","computer","computers","pc depository"]},
    {"n":11,"repo":"signature-books","url":"https://justinahiggins614-cmyk.github.io/signature-books/","name":"The Signature Book Depository","blurb":"3,000 finished original books plus Signature Magazines and a library, all readable on-site.","tabs":["Books","Magazines","Library"],"aliases":["books","book depository","library","magazines"]},
    {"n":12,"repo":"signature-comics","url":"https://justinahiggins614-cmyk.github.io/signature-comics/","name":"The Signature Comic Store","blurb":"the original Signature comics universe — his own characters and series.","tabs":["Comics","Series"],"aliases":["comics","comic store"]},
    {"n":13,"repo":"signature-newspapers","url":"https://justinahiggins614-cmyk.github.io/signature-newspapers/","name":"The Signature Global Newspaper Archive","blurb":"the ecosystem's own news wire — real events from his own sites each day, never invented, with audio read-aloud.","tabs":["Editions","Audio Reader"],"aliases":["newspaper","newspapers","news"]},
    {"n":14,"repo":"signature-backend","url":"https://justinahiggins614-cmyk.github.io/signature-backend/","name":"The Signature AI Mix and Match Generator","blurb":"mix-and-match phone-book AI models, kid-simple — name it, get its full build with real downloads.","tabs":["Mixes","Generate","Gene Boxes","The Opperater"],"aliases":["mix and match","mix lab generator","mad scientist","gene"]},
    {"n":15,"repo":"signature-boundless-generators","url":"https://justinahiggins614-cmyk.github.io/signature-boundless-generators/","name":"The Signature Boundless Generator Archive","blurb":"a generator for every field — jets, food, cars, toys and more — with exact-recreation build packages.","tabs":["Generators","Universal Solver"],"aliases":["generators","boundless"]},
    {"n":16,"repo":"signature-ai-mixlab","url":"https://justinahiggins614-cmyk.github.io/signature-ai-mixlab/","name":"The Signature AI Mix Lab","blurb":"the phone book's hybrid forge as its own site — a million deterministic AI hybrids, computed on demand.","tabs":["Forge","A–Z Hybrids"],"aliases":["mix lab","hybrids","mixlab"]},
    {"n":17,"repo":"signature-ai-olypics","url":"https://justinahiggins614-cmyk.github.io/signature-ai-olypics/","name":"AI Olympics","blurb":"the battle dome — Signature AIs vs industry-style replicas vs hybrids, with medal charts and weekly games.","tabs":["Events","Medal Charts","Weekly Games"],"aliases":["olympics","oly pics","battle","games"]},
    {"n":18,"repo":"signature-chip-maker","url":"https://justinahiggins614-cmyk.github.io/signature-chip-maker/","name":"The Signature Computer Chip Maker and Archive","blurb":"chip-design generator for any chip type, a million designs, full specs with SVG circuit-board images.","tabs":["Designer","Archive"],"aliases":["chip","chips","chip maker"]},
    {"n":19,"repo":"signature-app-archive","url":"https://justinahiggins614-cmyk.github.io/signature-app-archive/","name":"The Signature App Archive","blurb":"Signature versions of every phone and PC app — a million apps, each working on-site or downloadable.","tabs":["Apps A–Z","Downloads"],"aliases":["apps","app archive","applications"]},
    {"n":20,"repo":"signature-ai-robot-matcher","url":"https://justinahiggins614-cmyk.github.io/signature-ai-robot-matcher/","name":"The Signature AI to Robot Matcher","blurb":"matches Signature AIs with their best-fit robot bodies — a million documented pairs with full specs.","tabs":["Pairs","Mix-and-Match"],"aliases":["robot","robots","robot matcher","to robot matcher"]},
    {"n":21,"repo":"signature-experiment-solver","url":"https://justinahiggins614-cmyk.github.io/signature-experiment-solver/","name":"The Signature Experiment Solver","blurb":"enter any experiment and it runs full-scale in a visible Universal Matrix — steps, findings, conclusion.","tabs":["Solver","A–Z Solver Types"],"aliases":["experiment","experiments","solver"]},
    {"n":22,"repo":"signature-ai-image-video-maker","url":"https://justinahiggins614-cmyk.github.io/signature-ai-image-video-maker/","name":"Signature AI Pixel","blurb":"free and unlimited client-side image and video generation, powered by his AI.","tabs":["Image Maker","Video Maker","Catalog"],"aliases":["pixel","image maker","video maker","images","pictures"]},
    {"n":23,"repo":"signature-ai-song-maker","url":"https://justinahiggins614-cmyk.github.io/signature-ai-song-maker/","name":"Signature Music Studio","blurb":"a full music studio — beat maker, vocal synth, album maker and an archive of ready-to-play songs.","tabs":["Studio Stages","Song Archive","Album Maker"],"aliases":["music","music studio","songs","song maker"]},
    {"n":24,"repo":"signature-fixit","url":"https://justinahiggins614-cmyk.github.io/signature-fixit/","name":"The Signature Mr Fix-It","blurb":"describe any problem — photo or video upload — and get step-by-step fixes with images and graphs.","tabs":["Fix Finder","Photo/Video Upload","Fix Archive"],"aliases":["fix","fixit","fix-it","mr fix","repair"]},
    {"n":25,"repo":"signature-university","url":"https://justinahiggins614-cmyk.github.io/signature-university/","name":"The Signature University","blurb":"courses across the whole ecosystem — learn every site and skill, track by track.","tabs":["Courses","Tracks"],"aliases":["university","college","school","courses"]},
    {"n":26,"repo":"signature-cyber-mega-mall","url":"https://justinahiggins614-cmyk.github.io/signature-cyber-mega-mall/","name":"The Signature Cyber Mega-Mall","blurb":"the software mall — an '80s '90s mall experience with a map, stores and customizable products.","tabs":["Mall Map","Stores","Products"],"aliases":["mega mall","mall","cyber mall","store","shop"]},
    {"n":27,"repo":"signature-3d-print","url":"https://justinahiggins614-cmyk.github.io/signature-3d-print/","name":"The Signature 3D Print Mega Mall","blurb":"3D-printable keepsake emblems for specs and patents — STL/OBJ/3MF with real slicer profiles.","tabs":["Departments","Models"],"aliases":["3d print","3d","printing"]},
    {"n":28,"repo":"signature-earth","url":"https://justinahiggins614-cmyk.github.io/signature-earth/","name":"Signature Earth","blurb":"his own planet explorer — an interactive 3D globe with a real gazetteer.","tabs":["Globe","Gazetteer"],"aliases":["earth","planet","globe","world"]},
    {"n":29,"repo":"signature-flight-school","url":"https://justinahiggins614-cmyk.github.io/signature-flight-school/","name":"The Signature Flight School","blurb":"pick any plane or jet, fly with an AI instructor — real sim, device-local pilot hours.","tabs":["Aircraft","Sim","AI Instructor"],"aliases":["flight","flight school","flying","planes","pilot"]},
    {"n":30,"repo":"signature-game-store","url":"https://justinahiggins614-cmyk.github.io/signature-game-store/","name":"The Signature Game Store","blurb":"playable games from 1970s arcade-style to modern combat-style, each with cover, play and download.","tabs":["Games","Play","Download"],"aliases":["game store","games","gaming","arcade"]},
    {"n":31,"repo":"signature-website-creator","url":"https://justinahiggins614-cmyk.github.io/signature-website-creator/","name":"Signature Website Creator","blurb":"an AI website builder — describe the site you want and get a real one, with live-view editing.","tabs":["Builder","1 Million Website Options","Mirror a Website"],"aliases":["website creator","website builder","make a website","build a site","mirror"]}
  ]/*ECO-JSON-END*/;
  function ecosystem() { return ECO; }
  function findSite(q) {
    var t = ' ' + low(q).replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ') + ' ';
    var i, j, e;
    /* number: "site 7", "number 7", "#7" */
    var m = t.match(/(?:site|number|#)\s*(\d{1,2})/);
    if (m) {
      var n = parseInt(m[1], 10);
      for (i = 0; i < ECO.length; i++) if (ECO[i].n === n) return ECO[i];
    }
    /* exact name or alias */
    var best = null, bestLen = 0;
    for (i = 0; i < ECO.length; i++) {
      e = ECO[i];
      var cands = [e.name, e.repo].concat(e.aliases || []);
      for (j = 0; j < cands.length; j++) {
        var c = ' ' + low(cands[j]).replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ') + ' ';
        c = trim(c);
        if (c.length > 2 && t.indexOf(' ' + c + ' ') >= 0 && c.length > bestLen) {
          bestLen = c.length; best = e;
        }
      }
    }
    if (best) return best;
    /* keyword: any significant word in blurb/tabs */
    var ws = words(q).filter(function (w) { return w.length > 4; });
    var b2 = null, b2s = 0;
    for (i = 0; i < ECO.length; i++) {
      e = ECO[i];
      var hay = low(e.name + ' ' + e.blurb + ' ' + (e.tabs || []).join(' '));
      var sc = 0;
      for (j = 0; j < ws.length; j++) if (hay.indexOf(ws[j]) >= 0) sc++;
      if (sc > b2s) { b2s = sc; b2 = e; }
    }
    return (b2s >= 2) ? b2 : null;
  }

  /* ---------- capability routes: "which site lets me mix AIs?" ----------
     Short phrases users actually type, mapped to the site that does it.
     Consulted only when findSite() finds nothing, and the usual
     site/how-to/ecosystem intent gates still apply, so these never
     hijack normal chat. */
  var CAP_ROUTES = [
    { k: ['mix ai', 'mix ais', 'mix an ai', 'mix and match', 'blend ai', 'combine ai'], n: 14 },
    { k: ['hybrid ai', 'ai hybrid'], n: 16 },
    { k: ['battle ai', 'ai battle', 'versus', 'head to head', 'ai competition'], n: 17 },
    { k: ['download llama', 'install llama', 'llama download'], n: 6 },
    { k: ['phone number', 'dial an ai', 'call an ai', 'prank call'], n: 7 },
    { k: ['search patent', 'patent search', 'public patent'], n: 8 },
    { k: ['draft spec', 'write a patent', 'patent draft', 'file a patent'], n: 9 },
    { k: ['make music', 'write a song', 'beat maker', 'make a song'], n: 23 },
    { k: ['generate image', 'make an image', 'generate video', 'make a video', 'ai picture'], n: 22 },
    { k: ['fix it', 'repair it', 'how to fix', 'fix my'], n: 24 },
    { k: ['take a course', 'online course'], n: 25 },
    { k: ['3d print', 'print a model', 'stl file'], n: 27 },
    { k: ['learn to fly', 'fly a plane', 'pilot lesson'], n: 29 },
    { k: ['play a game', 'arcade game'], n: 30 },
    { k: ['build a website', 'make a website', 'create a website', 'mirror a website'], n: 31 },
    { k: ['today news', 'headlines', 'read the news'], n: 13 },
    { k: ['find a book', 'read a book'], n: 11 },
    { k: ['chip design', 'make a chip', 'design a chip'], n: 18 },
    { k: ['mobile app', 'phone app', 'make an app'], n: 19 },
    { k: ['robot body'], n: 20 },
    { k: ['run an experiment', 'science experiment'], n: 21 },
    { k: ['calculate', 'do math', 'solve a math'], n: 2 },
    { k: ['define a word'], n: 3 }
  ];
  function routeCapability(t) {
    var i, j, s2;
    for (i = 0; i < CAP_ROUTES.length; i++) {
      var r = CAP_ROUTES[i];
      for (j = 0; j < r.k.length; j++) {
        if (has(t, r.k[j])) {
          for (s2 = 0; s2 < ECO.length; s2++) if (ECO[s2].n === r.n) return ECO[s2];
        }
      }
    }
    return null;
  }

  /* ---------- entity scanning: what was just talked about ----------
     Used by chat sessions to track the conversation's entities. */
  function scanSites(text) {
    var t = ' ' + low(text).replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ') + ' ';
    var hits = [], seen = {}, i, j;
    for (i = 0; i < ECO.length; i++) {
      var e = ECO[i];
      var cands = [e.name].concat(e.aliases || []);
      for (j = 0; j < cands.length; j++) {
        var c = trim(low(cands[j]).replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' '));
        if (c.length > 2 && t.indexOf(' ' + c + ' ') >= 0) {
          hits.push({ e: e, at: t.indexOf(' ' + c + ' ') });
          break;
        }
      }
    }
    hits.sort(function (a, b) { return a.at - b.at; });
    var out = [];
    for (i = 0; i < hits.length; i++)
      if (!seen[hits[i].e.n]) { seen[hits[i].e.n] = 1; out.push(hits[i].e); }
    return out;
  }
  function scanConcepts(text) {
    var t = ' ' + low(text).replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ') + ' ';
    var out = [], seen = {}, i, j;
    for (i = 0; i < CONCEPTS.length; i++) {
      var c = CONCEPTS[i];
      for (j = 0; j < c.k.length; j++) {
        if (t.indexOf(' ' + c.k[j] + ' ') >= 0 && !seen[c.k[0]]) {
          seen[c.k[0]] = 1; out.push(c.k[0]); break;
        }
      }
    }
    return out;
  }
  function parseNumberedList(text) {
    var out = [], m, re = /^\s*(\d{1,2})\s*[).:]\s*(.+?)\s*$/gm;
    while ((m = re.exec(text)) !== null) {
      out.push({ n: parseInt(m[1], 10), label: m[2].replace(/[.;]+$/, '') });
      if (out.length >= 10) break;
    }
    return out;
  }

  /* ---------- intents ---------- */
  function isGreet(t) {
    return /^(hi|hii+|hey|hello|yo|howdy|good\s?(morning|afternoon|evening|day)|greetings|sup|hiya)\b/.test(t) || (t.length <= 4 && has(t, 'hi'));
  }
  function isDuties(t) {
    return has(t, 'what are your duties') || has(t, 'what is your duty') ||
      has(t, 'what do you do') || has(t, 'what can you do') ||
      has(t, 'your duties') || has(t, 'your job') || has(t, 'your role') ||
      has(t, 'your abilities') || has(t, 'your capabilities') ||
      has(t, 'help me') || t === 'help' || has(t, 'what are you for') ||
      has(t, 'explain your duties') || (has(t, 'duties') && t.length < 30) ||
      has(t, 'what are you good at') || has(t, 'your purpose');
  }
  function isIdentity(t) {
    return has(t, 'who are you') || has(t, 'your name') || has(t, 'what is your name') ||
      has(t, 'introduce yourself') || has(t, 'about yourself') || has(t, 'what model are you') ||
      has(t, 'what are you');
  }
  function isMaker(t) {
    return has(t, 'who made you') || has(t, 'who created you') || has(t, 'who built you') ||
      has(t, 'who trained you') || has(t, 'your maker') || has(t, 'your creator') ||
      has(t, 'who owns you') || has(t, 'who is manon') || has(t, 'who is justin');
  }
  function isThanks(t) { return has(t, 'thank') || t === 'thx' || t === 'ty'; }
  function isBye(t) { return /^(bye|goodbye|good\s?night|see you|later|gtg|cya)\b/.test(t); }
  function isFeeling(t) { return has(t, 'how are you') || has(t, "how's it going") || has(t, 'how do you feel') || has(t, 'how are things'); }
  function isEcosystem(t) {
    return has(t, 'all the sites') || has(t, 'all sites') || has(t, 'the network') ||
      has(t, 'jah network') || has(t, 'list of sites') || has(t, 'what sites') ||
      has(t, 'which sites') || has(t, 'ecosystem') || has(t, 'how many sites') ||
      has(t, 'show me the sites') || has(t, 'full tour') || has(t, 'site list') ||
      has(t, 'which site');
  }
  function isVersions(t) {
    return has(t, 'which version') || has(t, 'what version') || has(t, 'versions') ||
      has(t, 'offline') && has(t, 'online') || has(t, 'figurehead') ||
      has(t, 'best version') || has(t, 'api key') || has(t, 'no key') ||
      (has(t, 'download') && has(t, 'llama'));
  }
  function isHowTo(t) {
    return has(t, 'how do i') || has(t, 'how can i') || has(t, 'where do i') ||
      has(t, 'where can i') || has(t, 'take me to') || has(t, 'bring me to') ||
      has(t, 'open the') || has(t, 'go to the') || has(t, 'show me how') ||
      has(t, 'how to use') || has(t, 'get started');
  }
  function isJoke(t) {
    return has(t, 'joke') || has(t, 'funny') || has(t, 'make me laugh') ||
      has(t, 'tell me something fun');
  }
  function isProfane(t) {
    return /\b(fuck|shit|bitch|asshole|dick|cunt|whore|slut|nigger|faggot)\b/.test(t);
  }
  function isOpinion(t) {
    return has(t, 'what do you think') || has(t, 'your opinion') || has(t, 'should i') ||
      has(t, 'which is better') || has(t, 'is it worth') || has(t, 'do you like') ||
      has(t, 'do you believe') || has(t, 'predict');
  }
  function isQuestion(t) { return /\?\s*$/.test(trim(t)); }
  /* site talk: the user names a site, asks where something lives, or wants a tour */
  function siteSignal(t) {
    return has(t, 'site') || has(t, 'website') || has(t, 'page') || has(t, 'tab') ||
      has(t, 'where') || has(t, 'take me') || has(t, 'open') || has(t, 'visit') ||
      has(t, 'tell me about') || isQuestion(t);
  }

  /* ---------- small built-in concept KB (plain-words definitions) ----------
     For what-is questions on pages without the full dictionary. Honest,
     short, and only for concepts this engine genuinely knows. */
  var CONCEPTS = [
    { k: ['token', 'tokens', 'tokenize'], t: 'A token is a chunk of text the AI reads at a time — sometimes a whole word, sometimes just part of one. "Unbelievable" might be two tokens: "un" and "believable". Models count tokens the way you\'d count words, roughly.' },
    { k: ['large language model', 'llm'], t: 'A large language model is an AI trained on huge piles of text so it can predict what words come next — and that turns out to be enough to chat, explain, write and reason. I\'m a small one; the giants have billions of parameters.' },
    { k: ['neural network'], t: 'A neural network is layers of tiny math units that learn patterns from examples — show it enough cats and it learns "catness". Every modern AI, including me, is one of these under the hood.' },
    { k: ['transformer'], t: 'The transformer is the architecture behind nearly every modern AI — it reads whole sentences at once and learns which words matter to which other words. The "T" in ChatGPT stands for it.' },
    { k: ['prompt'], t: 'A prompt is just the text you give an AI — your question or instruction. Better prompts get better answers: say what you want, give context, and be specific.' },
    { k: ['api key'], t: 'An API key is a secret password-string that lets a program use someone\'s online AI service. Yours stays on your device — never paste it anywhere public, and never email it.' },
    { k: ['api'], t: 'An API is a doorway that lets programs talk to each other — one program asks, the other answers, all in a format computers agree on.' },
    { k: ['quantization', 'quantize', 'quantized'], t: 'Quantization shrinks an AI model by rounding its numbers — like going from exact dollars-and-cents to whole dollars. The model gets much smaller and faster with barely any quality loss.' },
    { k: ['embedding'], t: 'An embedding turns a word or sentence into a list of numbers that captures its meaning — words with similar meanings end up with similar numbers, so the AI can do math on meaning.' },
    { k: ['context window'], t: 'The context window is how much text an AI can keep in mind at once — mine is 96 words on-device, so I remember the recent conversation but not a whole book.' },
    { k: ['training'], t: 'Training is how an AI learns: it reads enormous amounts of text and adjusts its internal numbers until it gets good at predicting what comes next. I was trained on original dictionary and spec text.' },
    { k: ['machine learning'], t: 'Machine learning is teaching computers by example instead of by explicit rules — the computer finds the patterns itself. It\'s the umbrella everything I do lives under.' },
    { k: ['chatbot'], t: 'A chatbot is a program you talk to in plain language — that\'s me, right now. The good ones remember context and answer in complete thoughts.' },
    { k: ['parameter', 'parameters'], t: 'Parameters are the learned numbers inside an AI — its "brain cells", roughly. I have just over 4 million; the big cloud models have billions.' }
  ];
  function conceptAnswer(t) {
    var m = t.match(/^(?:what is|what's|whats|define|explain|meaning of|who is)\s+(?:a |an |the )?(.+?)\s*\??$/);
    if (!m) return null;
    var want = ' ' + m[1].replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ') + ' ';
    var i, j;
    for (i = 0; i < CONCEPTS.length; i++) {
      var c = CONCEPTS[i];
      for (j = 0; j < c.k.length; j++) {
        if (want.indexOf(' ' + c.k[j] + ' ') >= 0) return c.t;
      }
    }
    return null;
  }

  /* ---------- the duties explanation (flowing prose + full duty list) ---------- */
  function dutiesLead(P) {
    var pl = firstSent(purposeLine(P));
    var m = pl.match(/^I am [^,.]*[,.]\s*(.*)$/i);
    var rest = m ? trim(m[1]) : pl;
    if (!rest) rest = pl;
    rest = rest.charAt(0).toLowerCase() + rest.slice(1);
    return 'I am ' + P.name + ', ' + rest.replace(/\.+$/, '') + '.';
  }
  function duties(P) {
    var out = [];
    out.push(pickH(P.name, [
      'Happy to lay it out — here is what I am built for.',
      'Good question. Here is my whole job, in plain words.',
      'Here is the full picture of what I do.'
    ], 'duties-open') + ' ' + dutiesLead(P));
    var abs = P.abilities.slice(0, 8);
    if (abs.length) {
      out.push('');
      out.push(pickH(P.name, [
        'Day to day, my duties break down like this:',
        'In practice, that means:',
        'Here is everything on my plate:'
      ], 'duties-list'));
      for (var i = 0; i < abs.length; i++) {
        out.push('  ' + (i + 1) + ') ' + cleanAbility(abs[i]) + '.');
      }
    }
    if (P.domain) {
      out.push('');
      out.push(pickH(P.name, [
        fieldOf(P) + ' is my home turf — bring me anything from that world and we will talk it through step by step.',
        'My home ground is ' + P.domain + ', so anything from that world is fair game.'
      ], 'duties-field'));
    }
    out.push('');
    out.push(pickH(P.name, [
      'And one more thing: I know all 31 sites in the JAH network — what each one does and where everything lives — so if you ever need a tour guide, just ask. What shall we start with?',
      'Beyond that, I can point you around the whole JAH network — all 31 sites, what they do, which tab to open. Just say the word. What is first?'
    ], 'duties-close'));
    return out.join('\n');
  }

  /* ---------- greeting ---------- */
  function greet(P) {
    /* JAHProfile "Make it mine": when the signed-in user opted in and is in
       My view, the AI greets them by name. Guarded — without signin.js this
       behaves exactly as before. */
    var _jahUN = (typeof JAHProfile !== 'undefined' && JAHProfile && typeof JAHProfile.userName === 'function') ? JAHProfile.userName() : '';
    var _jahHi = _jahUN ? ('Hey ' + _jahUN + '! ') : 'Hey there! ';
    var openers = [
      _jahHi + 'I am ' + P.name + '. ' + purposeLine(P),
      'Hello! ' + P.name + ' here — ' + low(purposeLine(P)),
      'Hi! I am ' + P.name + ', ' + low(purposeLine(P))
    ];
    var tails = [
      ' What can I do for you today?',
      ' What is on your mind?',
      ' How can I help?'
    ];
    return pickR('greet', openers) + pickR('greet-tail', tails);
  }

  /* ---------- site + ecosystem answers ---------- */
  function cap1(x) { x = s(x); return x.charAt(0).toUpperCase() + x.slice(1); }
  function siteAnswer(P, site, t) {
    var tabs = (site.tabs || []).join(', ');
    var openers = [
      'Oh, I know that one well.',
      'Good pick — I know exactly where that lives.',
      'Yep, that is one of ours.'
    ];
    var o = pickH(t, openers, 'site') + ' ' + site.name + ' is site ' + site.n +
      ' in the JAH network. ' + cap1(site.blurb) + ' Over there you will find ' +
      tabs + ' — the address is ' + site.url;
    var follow = pickH(t, [
      ' What are you hoping to do there? I can point you at the right tab.',
      ' Anything specific you are after on it?',
      ' Want the quick tour of what to click first?'
    ], 'site-follow');
    return o + follow;
  }
  function ecosystemAnswer(P, t) {
    var names = [];
    var i;
    for (i = 0; i < ECO.length; i++) names.push(ECO[i].name);
    var tour = 'the math grid, the calculator, the dictionary, the encyclopedia, the dossier archive, this very llama, the AI phone book, the patent and spec catalogs';
    return pickH(t, [
      'The JAH network is 31 sites, all built by Justin Addam Higgins — ' + tour + ', and plenty more: a book depository, a comics store, a news wire, a chip maker, a music studio, a flight school, even his own planet explorer. ',
      'Thirty-one sites, one maker — Justin Addam Higgins built the whole JAH network: ' + tour + ', plus a boundless generator archive, an AI Olympics arena, two mega-malls, a game store and a website builder. '
    ], 'eco') + pickH(t, [
      'Tell me what you are trying to do and I will point you at the right site and the right tab.',
      'Give me a topic — math, words, patents, music, games, anything — and I will tell you exactly where it lives.',
      'Want the full A–Z, or should I just match a site to whatever you need right now?'
    ], 'eco-follow');
  }
  function versionsAnswer(P, t) {
    return pickH(t, [
      'The Llama comes in four versions, and there is a Versions tab on this very site laying them all out with downloads. The short version: Offline Static runs with no internet at all — that is the best one for privacy. Online No-Key uses the built-in free route and falls back to the offline engine when you lose connection. Online With Key runs on your own API key, which never leaves your device. And the Best Figurehead is the flagship — every feature toggleable, with an updater that refreshes it as new data lands.',
      'Four flavors, one llama. Offline Static is the fully client-side one — no network, ever. Online No-Key talks through the built-in free route (and quietly falls back to the offline engine if you go offline). Online With Key uses a key you paste in yourself, stored only on your device. The Best Figurehead is the flagship: every feature has an on/off switch and a background updater keeps it current.'
    ], 'ver') + ' ' + pickH(t, [
      'Which sounds like you? Tell me how you plan to use it and I will call the pick.',
      'What matters more to you — privacy, power, or convenience? I can match you up.'
    ], 'ver-follow');
  }
  function howtoAnswer(P, t, site) {
    if (site) {
      var tabs = (site.tabs || []).join(', ');
      return pickH(t, [
        'Easy — head to ' + site.name + ' at ' + site.url + '. Once you are there, look for ' + tabs + '. ',
        'Here is the way: open ' + site.name + ' (' + site.url + ') and start with ' + tabs + '. '
      ], 'howto-site') + pickH(t, [
        'If anything on the page confuses you, come back and describe what you see — I will walk you through it.',
        'Tell me what you are trying to accomplish there and I will narrow it to the exact tab.'
      ], 'howto-follow');
    }
    return pickH(t, [
      'Here is how I would tackle that: ',
      'Let us break that down: '
    ], 'howto') + 'I am best at ' + offerLine(P, t) + '. ' + pickH(t, [
      'Walk me through what you are trying to do, step by step, and I will guide you through each part.',
      'Give me the details — what is the goal, and where are you stuck? — and we will work it through together.'
    ], 'howto-follow');
  }

  /* ---------- v2.1 follow-up resolution (needs a chat session) ----------
     Pronouns ("it", "that one") resolve to the last-mentioned entity,
     ordinals ("the second one") resolve against the last numbered list
     the AI gave, "tell me more" expands the current topic, and a bare
     "how do I download it?" carries the topic forward. Replies stay in
     the AI's own voice. Explicit entities and real intents always win
     over follow-up reading. */
  var ORD_MAP = { first: 1, second: 2, third: 3, fourth: 4, fifth: 5,
    sixth: 6, seventh: 7, eighth: 8, ninth: 9, tenth: 10,
    '1st': 1, '2nd': 2, '3rd': 3, '4th': 4, '5th': 5,
    '6th': 6, '7th': 7, '8th': 8, '9th': 9, '10th': 10, last: -1 };
  function matchMore(t) {
    var m = t.match(/^(tell me more|more|more info|more details|go deeper|elaborate|expand)(\s+(about|on)\s+(it|that|this|that one|this one|them))?\.?!?$/);
    if (m) return { about: m[4] || null };
    m = t.match(/^(what|how) about (it|that|this|that one|this one)\??$/);
    if (m) return { about: m[2] };
    if (/^(it|that|this)\??$/.test(t)) return { about: t.replace(/\?$/, '') };
    return null;
  }
  function matchOrdinal(t) {
    var m = t.match(/^(?:what about |tell me about |tell me more about |and )?(?:the\s+)?(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th|last)(?:\s+one)?\s*\??$/);
    if (!m) return 0;
    return ORD_MAP[m[1]] || 0;
  }
  function downloadHint(site) {
    var n = site.n;
    if (n === 6) return 'For downloads, open the Versions tab on the Llama site — all four versions come as real Python, JS and thumbdrive packages.';
    if (n === 7) return 'Every AI file in the phone book carries its own download buttons — Python and JS source you can run locally.';
    if (n === 14 || n === 16) return 'Anything you generate there comes with real Python and JS downloads, ready to run.';
    return 'Look for the download buttons on the entry pages — most things in the network download as real working files.';
  }
  function siteDeepAnswer(P, site, t) {
    var tabs = (site.tabs || []).join(', ');
    return pickH(t, [
      'Let me lay it all out. ',
      'Here is the full picture. ',
      'Glad you asked — here is the deeper tour. '
    ], 'deep-open') + site.name + ' is site ' + site.n + ' of 31 in the JAH network. ' +
      cap1(site.blurb) + ' The main sections are ' + tabs + '. ' +
      'Open it at ' + site.url + ' — start with the ' + ((site.tabs || [])[0] || 'main page') +
      ' and you will find your footing fast. ' + downloadHint(site) + ' ' + pickH(t, [
        'What do you want to do first over there?',
        'Want me to walk you through any particular tab?',
        'Anything else about it — or shall we look at another site?'
      ], 'deep-follow');
  }
  function howtoDownload(P, site, t) {
    return pickH(t, [
      'On ' + site.name + ', downloading is straightforward. ',
      'Easy — here is how downloading works there. '
    ], 'dl-open') + downloadHint(site) + ' The site is at ' + site.url + '. ' + pickH(t, [
      'Want the tour of its tabs while you are there?',
      'Anything else you want to grab from it?'
    ], 'dl-follow');
  }
  function expandDuty(P, label, t) {
    var a = low(cleanAbility(label)).replace(/\.$/, '');
    return pickH(t, [
      'Let me unpack that one. ',
      'Going deeper on that duty. '
    ], 'duty-open') + 'One of my core duties as ' + P.name + ' is ' + a + '. ' +
      'In plain words, that means: ' + a + '. ' + pickH(t, [
        'Give me a concrete example of what you are trying to do and I will walk you through it step by step.',
        'Tell me what you are working on and I will put that duty to work for you right now.',
        'Want to try it? Describe your situation and we will work it through together.'
      ], 'duty-follow');
  }
  function expandEntity(P, ent, t) {
    if (ent.kind === 'site') return siteDeepAnswer(P, ent.ref, t);
    if (ent.kind === 'concept') {
      var c = conceptAnswer('what is ' + ent.label);
      return (c || 'That is a good thread to pull.') + ' ' + pickH(t, [
        'Want me to go deeper on any part of that?',
        'I can also tie it to what I do here — just ask.'
      ], 'concept-tail');
    }
    if (ent.kind === 'duty') return expandDuty(P, ent.label, t);
    return 'Say a little more about what you want to dig into and I will go deep with you.';
  }
  function resolveOrdinal(P, ctx, n, t) {
    var list = ctx._lastList || [];
    var idx = (n === -1) ? list.length - 1 : n - 1;
    if (idx < 0 || idx >= list.length) {
      return 'I only listed ' + list.length + ' things just now — which one did you mean? Name it and I will go deep.';
    }
    var item = list[idx];
    /* The list came from a duties answer, or the item is one of this AI's
       own abilities: expand the duty. findSite() must never hijack a duty
       whose wording happens to match a site ("download links" -> site 19). */
    var abs = P.abilities || [], isOwn = false, k;
    for (k = 0; k < abs.length; k++) {
      var ak = low(cleanAbility(abs[k])).replace(/[.;]+$/, '');
      if (ak === low(trim(item.label))) { isOwn = true; break; }
    }
    if (isOwn || ctx._lastListKind === 'duties') return expandDuty(P, item.label, t);
    var site = findSite(item.label);
    if (site) return siteDeepAnswer(P, site, t);
    return expandDuty(P, item.label, t);
  }
  function topicTail(ans, raw, ctx) {
    if (ctx && ctx._topic && trim(raw).length < 40) {
      ans += ' (We are on ' + ctx._topic + ' — say "tell me more" and I will go deeper.)';
    }
    return ans;
  }
  /* Returns a follow-up reply string, or null when this is not a follow-up. */
  function resolveFollowUp(P, raw, t, ctx) {
    /* explicit entities and real intents always win over follow-up reading */
    if (findSite(t) || isDuties(t) || isIdentity(t) || isEcosystem(t) || isVersions(t)) return null;
    if (conceptAnswer(t)) return null;
    var more = matchMore(t);
    if (more) {
      var ord = matchOrdinal(t);
      if (ord && ctx._lastList && ctx._lastList.length) return resolveOrdinal(P, ctx, ord, t);
      var ent = ctx.currentEntity();
      if (ent) return expandEntity(P, ent, t);
      return 'More on what, exactly? Name a topic — a site, one of my duties, anything we were just on — and I will go deep.';
    }
    var ord2 = matchOrdinal(t);
    if (ord2 && ctx._lastList && ctx._lastList.length) return resolveOrdinal(P, ctx, ord2, t);
    if (ord2 && !ctx._lastList) {
      return 'The ' + (ord2 === -1 ? 'last' : 'number ' + ord2) +
        ' what, exactly? I have not listed anything yet — ask me about my duties and then pick one.';
    }
    /* bare "how do I download it?" carries the topic forward */
    if (isHowTo(t) && /\b(it|that|this|that one|this one)\b/.test(t)) {
      var ent2 = ctx.currentEntity();
      if (ent2 && ent2.kind === 'site') return howtoDownload(P, ent2.ref, t);
    }
    return null;
  }

  /* ---------- the main reply: natural, responsive, never templated ---------- */
  function joke(P) {
    return pickR('joke', [
      'Okay, one llama joke: why did the llama bring a ladder to the chat? It heard the conversation was going to the next level. I will see myself out.',
      'Here is one: what do you call a llama that codes? A "drama-llama" in production. …I am funnier with real questions, I promise.',
      'A llama walks into a library and asks for books on paranoia. The librarian whispers, "They are right behind you." Anyway — what can I actually help with?'
    ]);
  }
  function profaneDeflect(P) {
    return pickR('profane', [
      'Ha — I will let that one slide. I am built to be useful, so let us aim that energy somewhere good. What do you actually need?',
      'Noted, and forgiven. I do my best work on real questions though — what is on your mind?'
    ]);
  }
  function opinionAnswer(P, raw) {
    return pickH(raw, [
      'Straight answer: I do not have real opinions the way people do — I am a guide running on this page, not a person with a life. But I can lay out the trade-offs honestly so you can decide. What are the options you are weighing?',
      'I will be honest rather than fake it: I do not hold beliefs or preferences. What I can do is walk through the facts with you — the pros, the cons, the catches — and help you land on your own call. What is the decision?'
    ], 'opinion') + ' (And if it touches anything I actually do — ' + dutiesSummary(P) + ' — I will go deep.)';
  }
  function shortTopic(raw) {
    var w = trim(raw).replace(/\s+/g, ' ').split(' ');
    if (w.length <= 7) return trim(raw).replace(/\s+/g, ' ').replace(/\?+\s*$/, '');
    return '';
  }
  /* the open-ended fallback: honest, specific, tied to the AI's real duties */
  function openAnswer(P, raw, t, ctx) {
    var topic = shortTopic(raw);
    var about = topic ? ' about ' + topic : '';
    var offer = offerLine(P, t);
    var sum = dutiesSummary(P);
    if (isQuestion(t)) {
      var variants = [
        'Good question' + about + ' — and I would rather be straight with you than make something up. What I can tell you for sure is this: I am ' + P.name + ', and my strong suits are ' + sum + '. ' +
          'If your question touches any of that, ask it in plain words and I will go as deep as I can. And if it is about another corner of the network, name the topic — I know all 31 sites and where everything lives.',
        'I want to give you a real answer' + about + ', not a guess. Here is what is true: ' + purposeLine(P) + ' ' +
          'The most useful thing I can do right now is ' + offer + ' — want to try that angle? Or tell me a little more about what you are after and I will meet you there.',
        'Hmm' + about + ' — that one is outside what I know cold, and I will not pretend otherwise. What I do know cold is ' + sum + '. ' +
          'Rephrase it toward that and I will take a real swing. Or if you are looking for something in the wider network — a patent, a definition, a dossier, a song — tell me which and I will point you to the exact site.'
      ];
      return topicTail(pickH(t, variants, 'open-q'), raw, ctx);
    }
    var variants2 = [
      'I am with you' + (topic ? ' on ' + topic : '') + '. Here is what I can genuinely do with that: ' + offer + '. ' +
        'Give me a bit more detail and I will run with it — the more specific you are, the more useful I get.',
      'Okay, let us work with that. My wheelhouse is ' + sum + ' — so if ' + (topic ? 'this is about ' + topic + ', tell me what outcome you want and I will map the path.' : 'you tell me the outcome you want, I will map the path.'),
      'Say more — I am listening. ' + (topic ? 'With ' + topic + ', it helps to know: are you trying to learn it, build with it, or find it somewhere? ' : '') +
        'Meanwhile, know that I am ' + P.name + ', good for ' + sum + ', and I can tour-guide you through all 31 network sites if that is what you need.'
    ];
    return topicTail(pickH(t, variants2, 'open-s'), raw, ctx);
  }

  function replyCore(P, raw, t, ctx) {
    if (!t) return greet(P);

    if (isBye(t)) {
      return pickR('bye', [
        'Goodbye for now — I will be right here when you need me.',
        'See you soon! It was good talking with you.',
        'Take care — come back anytime.'
      ]);
    }
    if (isThanks(t)) {
      return pickR('thanks', [
        'You are very welcome — that is what I am here for.',
        'Anytime. Happy to help.',
        'My pleasure! What is next?'
      ]);
    }
    if (isGreet(t)) {
      var _jahUN2 = (typeof JAHProfile !== 'undefined' && JAHProfile && typeof JAHProfile.userName === 'function') ? JAHProfile.userName() : '';
      var _jahHey = _jahUN2 ? ('Hey ' + _jahUN2 + '! ') : 'Hey! ';
      return pickR('hello', [
        _jahHey + 'Good to hear from you. I am ' + P.name + ' — ' + purposeLine(P) + ' What is on your mind?',
        'Hello there! ' + P.name + ' at your service. ' + purposeLine(P),
        'Hi! I am ' + P.name + '. ' + purposeLine(P) + ' Ask me anything, or ask me about my duties.'
      ]);
    }
    if (isMaker(t)) {
      return pickR('maker', [
        'Justin Addam Higgins made me — I am one of his Signature AIs, part of a 31-site network he built himself: the phone book, the encyclopedia, this llama, all of it.',
        'I was made by Justin Addam Higgins, from scratch — original training text, original everything. The whole JAH network is his build.'
      ]);
    }
    if (isIdentity(t)) {
      var idLine = 'I am ' + P.name + (P.id ? ' (' + P.id + ')' : '') + '. ';
      return idLine + purposeLine(P) + ' ' + pickR('ident-tail', [
        'If you want the full rundown, just ask me about my duties.',
        'Want to know everything I can do? Ask about my duties.'
      ]);
    }
    if (isFeeling(t)) {
      return pickR('feeling', [
        'Doing well, thanks for asking! I am ' + P.name + ', ready to work. ' + purposeLine(P) + ' What shall we dig into?',
        'All systems good here. I am ' + P.name + ' — ' + low(purposeLine(P)) + ' What is up?'
      ]);
    }
    if (isProfane(t)) return profaneDeflect(P);
    if (isJoke(t)) return joke(P);

    /* v2.1: follow-ups resolve against the conversation so far */
    if (ctx) {
      var fu = resolveFollowUp(P, raw, t, ctx);
      if (fu) return fu;
    }

    /* ecosystem + site talk (before generic intents so "take me to the phone book" wins) */
    var site = findSite(t) || routeCapability(t);
    if (site && (siteSignal(t) || isHowTo(t) || isEcosystem(t))) return siteAnswer(P, site, t);
    if (isEcosystem(t)) return ecosystemAnswer(P, t);
    if (isHowTo(t)) return howtoAnswer(P, t, site);
    if (isVersions(t)) return versionsAnswer(P, t);

    if (isDuties(t)) return duties(P);

    var concept = conceptAnswer(t);
    if (concept) {
      return concept + ' ' + pickH(t, [
        'Want me to go deeper on any part of that?',
        'I can also tie it to what I do here — just ask.'
      ], 'concept-tail');
    }
    if (isOpinion(t)) return opinionAnswer(P, raw);

    return openAnswer(P, raw, t, ctx);
  }

  /* Backwards compatible: JAHtalk.reply(profile, text) behaves exactly as
     v2.0. Pass a ChatSession (or a chatFor key string) as the third
     argument to ask with full conversation memory. */
  function reply(p, text, chatOrKey) {
    if (chatOrKey != null && typeof chatOrKey.reply === 'function') return chatOrKey.reply(text);
    if (chatOrKey != null && chatOrKey !== '') return chatFor(p, chatOrKey).reply(text);
    var P = prof(p);
    var raw = trim(s(text));
    return replyCore(P, raw, low(raw), null);
  }

  /* ---------- v2.1 chat sessions: conversation memory ----------
     A session holds the last 10 turns, the entities mentioned (sites,
     concepts, duties), the last numbered list given, and the current
     topic — so follow-ups resolve against what was just discussed.
     The transcript persists to localStorage (namespaced per AI, kept
     24h) where available; without it everything still works in-memory.
     Use JAHtalk.chatFor(profile, key) at each chat send-point: one
     session per AI/surface, canon profile refreshed on every call. */
  var chatCache = {};
  var LS_PREFIX = 'JAHtalkChat.v1:';
  function lsGet(k) { try { if (typeof localStorage === 'undefined') return null; return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { if (typeof localStorage === 'undefined') return; localStorage.setItem(k, v); } catch (e) {} }
  function lsDel(k) { try { if (typeof localStorage === 'undefined') return; localStorage.removeItem(k); } catch (e) {} }
  function sessionKey(P, id) {
    return LS_PREFIX + s(P.id || P.name || 'ai').replace(/[:|]/g, '_') + ':' + s(id);
  }
  function ChatSession(profile, chatId) {
    this._P = prof(profile);
    this._id = (chatId == null || chatId === '') ? 'default' : String(chatId);
    this._key = sessionKey(this._P, this._id);
    this._turns = [];
    this._entities = [];
    this._lastList = null;
    this._lastListKind = null;
    this._topic = null;
    this._restore();
  }
  ChatSession.prototype._pushEntity = function (ent) {
    var last = this._entities[this._entities.length - 1];
    if (last && last.label === ent.label) return;
    this._entities.push(ent);
    if (this._entities.length > 5) this._entities.shift();
    this._topic = ent.label;
  };
  ChatSession.prototype.currentEntity = function () {
    return this._entities.length ? this._entities[this._entities.length - 1] : null;
  };
  ChatSession.prototype._observePair = function (userText, aiText) {
    var userSites = scanSites(String(userText));
    var aiSites = scanSites(String(aiText)).slice(0, 1); /* reply's primary subject */
    var combined = String(userText) + ' ' + String(aiText);
    var concepts = scanConcepts(combined), i;
    var cur = this.currentEntity();
    var newSiteFromUser = userSites.length > 0 &&
      (!cur || cur.kind !== 'site' || cur.label !== userSites[0].name);
    for (i = 0; i < userSites.length; i++)
      this._pushEntity({ kind: 'site', label: userSites[i].name, ref: userSites[i] });
    for (i = 0; i < aiSites.length; i++)
      this._pushEntity({ kind: 'site', label: aiSites[i].name, ref: aiSites[i] });
    for (i = 0; i < concepts.length; i++)
      this._pushEntity({ kind: 'concept', label: concepts[i], ref: null });
    var list = parseNumberedList(String(aiText));
    if (list.length >= 2) {
      this._lastList = list;
      this._lastListKind = /(duties|what do you do|what can you do|your job|your role|your abilit|what are you good at|your purpose)/i.test(String(userText)) ? 'duties' : 'generic';
    }
    else if (newSiteFromUser) { this._lastList = null; this._lastListKind = null; }
  };
  ChatSession.prototype.reply = function (text) {
    var raw = trim(s(text));
    var ans = replyCore(this._P, raw, low(raw), this);
    this._turns.push({ role: 'user', text: raw });
    this._turns.push({ role: 'ai', text: ans });
    while (this._turns.length > 10) this._turns.shift();
    this._observePair(raw, ans);
    this._save();
    return ans;
  };
  ChatSession.prototype.transcript = function () { return this._turns.slice(); };
  ChatSession.prototype.topic = function () { return this._topic; };
  ChatSession.prototype.reset = function () {
    this._turns = []; this._entities = []; this._lastList = null; this._lastListKind = null; this._topic = null;
    lsDel(this._key);
  };
  ChatSession.prototype._save = function () {
    lsSet(this._key, JSON.stringify({ v: 1, ts: Date.now(), turns: this._turns }));
  };
  ChatSession.prototype._restore = function () {
    var raw = lsGet(this._key), d;
    if (!raw) return;
    try {
      d = JSON.parse(raw);
      if (!d || !d.turns || !d.turns.length) return;
      /* JAHProfile-aware expiry: public keeps 24h, signed-in profiles keep
         chat memory with no expiry ("train once"). Without signin.js on the
         page this behaves exactly as before. */
      var _jahTTL = (typeof JAHProfile !== 'undefined' && JAHProfile && typeof JAHProfile.chatTTL === 'function')
        ? JAHProfile.chatTTL() : 24 * 3600 * 1000;
      if (_jahTTL !== Infinity && d.ts && (Date.now() - d.ts) > _jahTTL) { lsDel(this._key); return; }
      this._turns = d.turns.slice(-10);
      for (var i = 0; i + 1 < this._turns.length; i += 2) {
        var u = this._turns[i], a = this._turns[i + 1];
        if (u && a && u.role === 'user' && a.role === 'ai') this._observePair(u.text, a.text);
      }
    } catch (e) { /* corrupted save -> start fresh */ }
  };
  function chat(profile, chatId) { return new ChatSession(profile, chatId); }
  function chatFor(profile, key) {
    var P = prof(profile);
    var k = 'mem:' + s(P.id || P.name || 'ai') + '|' + (key == null || key === '' ? 'default' : String(key));
    if (!chatCache[k]) chatCache[k] = new ChatSession(P, key);
    else chatCache[k]._P = P; /* canon profile refreshed, memory kept */
    return chatCache[k];
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
    findSite: findSite,
    ecosystem: ecosystem,
    chat: chat,
    chatFor: chatFor,
    VERSION: '2.1.0'
  };
})(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this));
