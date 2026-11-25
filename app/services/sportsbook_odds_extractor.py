import re

SPORTSBOOK_ODDS_HEADER = "Displayed Sportsbook Odds"

_OUTCOME_LABELS = {
    "h": "{home}",
    "a": "{away}",
    "d": "Draw",
    "ov": "Over",
    "ud": "Under",
    "y": "Yes",
    "n": "No",
    "h-d": "{home}/Draw",
    "a-d": "{away}/Draw",
    "h-a": "{home}/{away}",
    "bt": "Both Teams",
    "od": "Odd",
    "ev": "Even",
    "1st": "1st Half",
    "2nd": "2nd Half",
    "h-h": "{home}/{home}",
    "h-d_htft": "{home}/Draw",
    "h-a_htft": "{home}/{away}",
    "d-h": "Draw/{home}",
    "d-d": "Draw/Draw",
    "d-a": "Draw/{away}",
    "a-h": "{away}/{home}",
    "a-a": "{away}/{away}",
}

# Place very high-cardinality exact score combination matrices at the end so all
# primary markets stay ahead of any link-level character limit.
_LATE_MARKET_PREFIXES = ("hfcs", "hf&nog", "hf&ou")

_MATCH_DOM_SCRIPT = """async () => {
    const root = document.querySelector('[data-testid="SportExhaustivePage"]');
    const content = document.querySelector('[data-testid="ExhaustiveContentV4"]');
    if (!root || !content) return null;

    const cleanText = (el) => ((el && el.innerText) || '').replace(/\\s+/g, ' ').trim();
    const navText = cleanText(root.querySelector('[data-testid^="exhaustive-navigator"]'));
    const sbEl = root.querySelector('[data-testid^="sport-scoreboard"]');
    const scoreboard = (sbEl && sbEl.innerText ? sbEl.innerText : '').trim();

    const readButtons = (scopeEl) => {
        const out = [];
        for (const btn of scopeEl.querySelectorAll('[data-testid^="oddsBtn-"]')) {
            const text = cleanText(btn);
            if (!text) continue;
            out.push({ id: btn.getAttribute('data-testid') || '', text });
        }
        return out;
    };

    const readPercentages = (wrapper) => {
        const seenPct = new Set();
        const items = [];
        for (const el of wrapper.querySelectorAll('[data-testid^="sport-market-bet-amount-percentage-value-"]')) {
            const pid = el.getAttribute('data-testid') || '';
            const side = pid.replace('sport-market-bet-amount-percentage-value-', '');
            const val = ((el.firstElementChild && el.firstElementChild.innerText) || el.innerText || '').trim();
            const key = side + ':' + val;
            if (val && !seenPct.has(key)) {
                seenPct.add(key);
                items.push({ side, value: val });
            }
        }
        return items;
    };

    const seenCards = new Map();
    const readWrapper = async (wrapper, order) => {
        const wid = wrapper.getAttribute('data-testid') || '';
        const hdr = wrapper.querySelector('[data-testid="exhaustive-market-card-header"]');
        if (!hdr) return;
        const title = cleanText(hdr.querySelector('.truncate')) || cleanText(hdr) || wid;

        if (wrapper.querySelectorAll('[data-testid^="oddsBtn-"]').length === 0) {
            wrapper.scrollIntoView({ block: 'center' });
            hdr.click();
            await new Promise((r) => setTimeout(r, 140));
        }

        const allBtn = wrapper.querySelector('[data-testid="all"]');
        if (allBtn) {
            allBtn.click();
            await new Promise((r) => setTimeout(r, 120));
        }

        const percentages = readPercentages(wrapper);
        const subTabs = Array.from(wrapper.querySelectorAll('[data-testid^="MarketLayoutRowAndColContainerTabs-"]'));
        const tabs = [];
        if (subTabs.length > 0) {
            for (const tabEl of subTabs) {
                tabEl.click();
                await new Promise((r) => setTimeout(r, 100));
                const buttons = readButtons(wrapper);
                if (buttons.length > 0) {
                    tabs.push({ tab: cleanText(tabEl), buttons });
                }
            }
        } else {
            const buttons = readButtons(wrapper);
            if (buttons.length > 0) {
                tabs.push({ tab: '', buttons });
            }
        }

        const totalButtons = tabs.reduce((sum, item) => sum + item.buttons.length, 0);
        const prev = seenCards.get(wid);
        if (!prev || totalButtons > prev.totalButtons) {
            seenCards.set(wid, { wid, title, order: prev ? prev.order : order, percentages, tabs, totalButtons });
        }
    };

    let y = 0;
    let nextOrder = 0;
    for (let step = 0; step < 35; step++) {
        const wrappers = Array.from(content.querySelectorAll('[data-testid^="ExhaustiveMarketCardWrapper-"]'))
            .filter((el) => !el.parentElement || !el.parentElement.closest('[data-testid^="ExhaustiveMarketCardWrapper-"]'));
        for (const wrapper of wrappers) {
            const wid = wrapper.getAttribute('data-testid') || '';
            if (!seenCards.has(wid) || seenCards.get(wid).totalButtons === 0) {
                await readWrapper(wrapper, nextOrder++);
            }
        }
        const maxScroll = Math.max(document.body.scrollHeight || 0, document.documentElement.scrollHeight || 0);
        if (y >= maxScroll) break;
        y += 650;
        window.scrollTo(0, y);
        await new Promise((r) => setTimeout(r, 180));
    }

    return {
        kind: 'match',
        competition: navText,
        scoreboard,
        markets: Array.from(seenCards.values()).sort((a, b) => a.order - b.order),
    };
}"""

_LIST_DOM_SCRIPT = """async () => {
    const cards = Array.from(document.querySelectorAll('[data-testid^="simple-handicap-layout-"]'));
    if (!cards.length) return null;

    const cleanText = (el) => ((el && el.innerText) || '').replace(/\\s+/g, ' ').trim();
    const events = new Map();

    let y = 0;
    for (let step = 0; step < 20; step++) {
        for (const card of document.querySelectorAll('[data-testid^="simple-handicap-layout-"]')) {
            const cid = card.getAttribute('data-testid') || '';
            const home = cleanText(card.querySelector('[data-testid="sport-event-card-home-name"]'));
            const away = cleanText(card.querySelector('[data-testid="sport-event-card-away-name"]'));
            if (!home && !away) continue;
            const unit = card.closest('[data-testid^="v4-sport-international-simple-handicap-unit-"]');
            const competition = cleanText(unit?.querySelector('[data-testid="simple-handicap-odds-header"]'));
            const buttons = [];
            for (const btn of card.querySelectorAll('[data-testid^="oddsBtn-"]')) {
                const text = cleanText(btn);
                if (text) buttons.push({ id: btn.getAttribute('data-testid') || '', text });
            }
            const rawLines = (card.innerText || '').split('\\n').map((s) => s.trim()).filter(Boolean);
            const kickoff = rawLines.find((line) => /\\d{1,2}\\s+[A-Za-z]{3}\\s+\\d{2}:\\d{2}|\\d{2}:\\d{2}/.test(line)) || '';
            if (buttons.length && (!events.has(cid) || buttons.length > events.get(cid).buttons.length)) {
                events.set(cid, { cid, competition, kickoff, home_team: home, away_team: away, buttons });
            }
        }
        const maxScroll = Math.max(document.body.scrollHeight || 0, document.documentElement.scrollHeight || 0);
        if (y >= maxScroll) break;
        y += 650;
        window.scrollTo(0, y);
        await new Promise((r) => setTimeout(r, 150));
    }

    if (!events.size) return null;
    return { kind: 'list', events: Array.from(events.values()) };
}"""


def is_sportsbook_odds_context(text: str) -> bool:
    return SPORTSBOOK_ODDS_HEADER in (text or "")


def extract_sportsbook_odds_from_page(page, url: str = "") -> dict | None:
    if not hasattr(page, "evaluate"):
        return None

    lowered_url = (url or "").lower()
    if hasattr(page, "wait_for_selector") and ("/sportevents/" in lowered_url or "2bet" in lowered_url):
        try:
            page.wait_for_selector(
                '[data-testid="ExhaustiveContentV4"], [data-testid^="simple-handicap-layout-"]',
                timeout=6000,
            )
        except Exception:
            pass

    try:
        raw_data = page.evaluate(_MATCH_DOM_SCRIPT)
        if not raw_data:
            raw_data = page.evaluate(_LIST_DOM_SCRIPT)
    except Exception:
        return None

    return format_sportsbook_odds_data(raw_data)


def format_sportsbook_odds_data(raw_data: dict | None) -> dict | None:
    if not isinstance(raw_data, dict):
        return None
    kind = raw_data.get("kind")
    if kind == "match":
        return _format_match_odds_data(raw_data)
    if kind == "list":
        return _format_list_odds_data(raw_data)
    return None


def _parse_scoreboard(scoreboard: str) -> tuple[str, str, str, str]:
    lines = [line.strip() for line in (scoreboard or "").splitlines() if line.strip()]
    if not lines:
        return "", "", "", ""

    vs_index = next((idx for idx, line in enumerate(lines) if line.lower() == "vs"), -1)
    if vs_index >= 0:
        before_vs = lines[:vs_index]
        after_vs = lines[vs_index + 1 :]
        home_team = before_vs[0] if before_vs else ""
        kickoff = " ".join(before_vs[1:]) if len(before_vs) > 1 else ""
        away_team = after_vs[-1] if after_vs else ""
        stage = " ".join(after_vs[:-1]) if len(after_vs) > 1 else ""
        return home_team, away_team, kickoff, stage

    home_team = lines[0] if lines else ""
    away_team = lines[-1] if len(lines) > 1 else ""
    kickoff = " ".join(lines[1:-1]) if len(lines) > 2 else ""
    return home_team, away_team, kickoff, ""


def _parse_button_id(btn_id: str) -> tuple[str, str, str]:
    parts = (btn_id or "").split("|")
    market = parts[2] if len(parts) > 2 else ""
    outcome = parts[3] if len(parts) > 3 else ""
    line = parts[5] if len(parts) > 5 else ""
    return market, outcome, line


def _split_button_label_and_odds(btn_text: str) -> tuple[str, str]:
    cleaned = " ".join((btn_text or "").split()).strip()
    match = re.match(r"^(.*?)\s*(\d+(?:\.\d+)?)$", cleaned)
    if not match:
        return cleaned, ""
    return match.group(1).strip(), match.group(2).strip()


def _resolve_outcome_token(token: str, home_team: str, away_team: str) -> str:
    home = home_team or "Home"
    away = away_team or "Away"
    lowered = token.lower()
    if lowered in {"h-d", "h-a", "d-h", "d-d", "d-a", "a-h", "a-a", "h-h"}:
        template = _OUTCOME_LABELS.get(f"{lowered}_htft") or _OUTCOME_LABELS.get(lowered) or token
        return template.format(home=home, away=away)
    template = _OUTCOME_LABELS.get(lowered)
    if template:
        return template.format(home=home, away=away)
    return token


def _resolve_market_prefix(market: str, home_team: str, away_team: str) -> str:
    if market.startswith("h-") and home_team:
        return home_team
    if market.startswith("a-") and away_team:
        return away_team
    return ""


def _should_use_label_only(label: str, outcome_text: str) -> bool:
    if not label:
        return False
    lowered_label = label.lower()
    if re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?)?", label):
        return False
    if lowered_label in {"1", "x", "2", "y", "n"}:
        return False
    if outcome_text.lower() in {"draw", "home", "away", "yes", "no"} and len(label) > 2 and label not in {"1/X", "X/2", "1/2"}:
        if any(token in lowered_label for token in ("no goal", "goal", "score", "half", "other", "yes", "no", "odd", "even")):
            return True
    if any(ch in label for ch in ("-", "&", ",", "Goal", "Half", "Other", "Both", "O ", "U ")):
        return True
    return False


def format_odds_selection(btn_id: str, btn_text: str, home_team: str = "", away_team: str = "") -> str:
    label, odds = _split_button_label_and_odds(btn_text)
    if not odds:
        return ""

    market, outcome, line = _parse_button_id(btn_id)
    team_prefix = _resolve_market_prefix(market, home_team, away_team)

    outcome_parts = [part for part in outcome.split("&") if part]
    if len(outcome_parts) > 1:
        resolved_parts = [_resolve_outcome_token(part, home_team, away_team) for part in outcome_parts]
        descriptor = " & ".join(resolved_parts)
        if label:
            if any(part.lower() in {"o", "u"} or label.startswith(("O ", "U ")) for part in [label]):
                descriptor = f"{descriptor} ({label})"
            elif line and line not in label:
                descriptor = f"{descriptor} {label} {line}".strip()
            elif label.lower() not in descriptor.lower():
                descriptor = f"{descriptor} ({label})"
    else:
        resolved = _resolve_outcome_token(outcome, home_team, away_team) if outcome else ""
        if _should_use_label_only(label, resolved):
            descriptor = label
        elif outcome.lower() in {"h", "a"} and label in {"1", "2"}:
            descriptor = f"{resolved} ({label})"
        elif outcome.lower() == "d" and label == "X":
            descriptor = f"{resolved} (X)"
        elif resolved and label and label.lower() != resolved.lower():
            descriptor = f"{resolved} {label}"
        else:
            descriptor = resolved or label

    if team_prefix and team_prefix.lower() not in (descriptor or "").lower():
        descriptor = f"{team_prefix} {descriptor}".strip()

    if not descriptor:
        return odds
    return f"{descriptor} @ {odds}"


def _format_percentages(percentages: list[dict], market_title: str, home_team: str, away_team: str) -> str:
    if not percentages:
        return ""
    lowered_title = (market_title or "").lower()
    is_over_under = "over/under" in lowered_title or "o / u" in lowered_title or "o/u" in lowered_title
    parts = []
    for item in percentages:
        side = (item.get("side") or "").lower()
        value = (item.get("value") or "").strip()
        if not value:
            continue
        if side == "home":
            label = "Over" if is_over_under else (home_team or "Home")
        elif side == "away":
            label = "Under" if is_over_under else (away_team or "Away")
        elif side == "draw":
            label = "Draw"
        else:
            label = side.title()
        parts.append(f"{label} {value}")
    return f"Betting split: {', '.join(parts)}" if parts else ""


def _market_sort_key(market: dict) -> tuple[int, int]:
    wid = (market.get("wid") or "").lower()
    slug = wid.replace("exhaustivemarketcardwrapper-", "")
    is_late = any(slug.startswith(prefix) for prefix in _LATE_MARKET_PREFIXES)
    return (1 if is_late else 0, int(market.get("order", 0)))


def _format_match_odds_data(raw_data: dict) -> dict | None:
    competition = " ".join((raw_data.get("competition") or "").split()).strip()
    home_team, away_team, kickoff, stage = _parse_scoreboard(raw_data.get("scoreboard") or "")

    markets = raw_data.get("markets") or []
    lines = [SPORTSBOOK_ODDS_HEADER]
    if competition or stage:
        comp_line = " - ".join(part for part in (competition, stage) if part)
        lines.append(f"Competition: {comp_line}")
    if home_team or away_team:
        match_label = f"{home_team or 'Home'} vs {away_team or 'Away'}"
        if kickoff:
            match_label += f" ({kickoff})"
        lines.append(f"Match: {match_label}")
    if home_team or away_team:
        lines.append(f"Legend: 1 = {home_team or 'Home'}, X = Draw, 2 = {away_team or 'Away'}")

    market_lines_added = 0
    for market in sorted(markets, key=_market_sort_key):
        title = " ".join((market.get("title") or "").split()).strip()
        if not title:
            continue
        tabs_out = []
        for tab_entry in market.get("tabs") or []:
            tab_name = " ".join((tab_entry.get("tab") or "").split()).strip()
            formatted_items = []
            seen_items = set()
            for btn in tab_entry.get("buttons") or []:
                item_text = format_odds_selection(btn.get("id", ""), btn.get("text", ""), home_team, away_team)
                if item_text and item_text not in seen_items:
                    seen_items.add(item_text)
                    formatted_items.append(item_text)
            if formatted_items:
                prefix = f"[{tab_name}] " if tab_name else ""
                tabs_out.append(f"{prefix}{' | '.join(formatted_items)}")

        if not tabs_out:
            continue

        pct_line = _format_percentages(market.get("percentages") or [], title, home_team, away_team)
        block_parts = [f"## {title}"]
        if pct_line:
            block_parts.append(pct_line)
        block_parts.extend(tabs_out)
        lines.append("\n".join(block_parts))
        market_lines_added += 1

    if market_lines_added == 0:
        return None

    page_title = (
        f"{home_team} vs {away_team} Odds"
        if (home_team or away_team)
        else (competition or "Sportsbook Match Odds")
    )
    if competition and (home_team or away_team):
        page_title += f" | {competition}"
    return {
        "title": page_title,
        "text": "\n\n".join(lines),
        "structured_odds": True,
    }


def _format_list_odds_data(raw_data: dict) -> dict | None:
    events = raw_data.get("events") or []
    lines = [f"{SPORTSBOOK_ODDS_HEADER} (Match List)"]
    added = 0
    for event in events:
        home_team = " ".join((event.get("home_team") or "").split()).strip()
        away_team = " ".join((event.get("away_team") or "").split()).strip()
        competition = " ".join((event.get("competition") or "").split()).strip()
        kickoff = " ".join((event.get("kickoff") or "").split()).strip()
        seen_items = set()
        odds_items = []
        for btn in event.get("buttons") or []:
            item_text = format_odds_selection(btn.get("id", ""), btn.get("text", ""), home_team, away_team)
            if item_text and item_text not in seen_items:
                seen_items.add(item_text)
                odds_items.append(item_text)
        if not odds_items:
            continue
        header_parts = [part for part in (competition, kickoff, f"{home_team} vs {away_team}") if part]
        lines.append(f"- {' | '.join(header_parts)}: {' ; '.join(odds_items)}")
        added += 1

    if added == 0:
        return None
    return {
        "title": "Sportsbook Match Odds List",
        "text": "\n".join(lines),
        "structured_odds": True,
    }
