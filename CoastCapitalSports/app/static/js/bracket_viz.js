/* ============================================================
   bracket_viz.js — NCAA Tournament Bracket Visualization
   ESPN/Yahoo-style bracket renderer (pure HTML/CSS via JS)
   ============================================================ */

(function () {
    'use strict';

    // ------------------------------------------------------------------
    // CSS Injection (runs once)
    // ------------------------------------------------------------------
    let stylesInjected = false;

    function injectStyles() {
        if (stylesInjected) return;
        stylesInjected = true;

        const style = document.createElement('style');
        style.textContent = `
/* ---- Bracket Container ---- */
.bracket-container {
    display: flex;
    align-items: stretch;
    overflow-x: auto;
    padding: 24px 12px;
    gap: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    background: #1a1d21;
    color: #e2e8f0;
    min-height: 600px;
    position: relative;
    -webkit-overflow-scrolling: touch;
}

.bracket-container *,
.bracket-container *::before,
.bracket-container *::after {
    box-sizing: border-box;
}

/* ---- Halves (left flows right, right flows left) ---- */
.bracket-half {
    display: flex;
    flex-direction: column;
    gap: 32px;
}
.bracket-half--left {
    flex: 1 1 0;
}
.bracket-half--right {
    flex: 1 1 0;
}

.bracket-center {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-width: 220px;
    gap: 20px;
    padding: 0 8px;
    z-index: 2;
}

/* ---- Region ---- */
.bracket-region {
    display: flex;
    flex-direction: row;
    align-items: stretch;
    gap: 0;
}
.bracket-region--right {
    flex-direction: row-reverse;
}

.bracket-region-label {
    font-size: 14px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #94a3b8;
    padding: 4px 12px 12px;
    text-align: center;
}

/* ---- Round Column ---- */
.bracket-round {
    display: flex;
    flex-direction: column;
    justify-content: space-around;
    min-width: 175px;
    padding: 0 2px;
    position: relative;
}

/* ---- Matchup Card ---- */
.bracket-matchup {
    display: flex;
    flex-direction: column;
    background: #22262b;
    border: 1px solid #2d3239;
    border-radius: 5px;
    margin: 4px 3px;
    overflow: hidden;
    position: relative;
    transition: box-shadow 0.15s ease, border-color 0.15s ease;
    min-width: 168px;
}
.bracket-matchup:hover {
    border-color: #475569;
    box-shadow: 0 2px 12px rgba(0,0,0,0.35);
    z-index: 3;
}

/* Left-border accent for winner / upset */
.bracket-matchup--has-winner {
    border-left: 3px solid #22c55e;
}
.bracket-matchup--upset {
    border-left: 3px solid #f97316;
}

/* Background tint for correct / incorrect */
.bracket-matchup--correct {
    background: linear-gradient(135deg, rgba(34,197,94,0.12) 0%, #22262b 60%);
}
.bracket-matchup--incorrect {
    background: linear-gradient(135deg, rgba(239,68,68,0.14) 0%, #22262b 60%);
}

/* ---- Team Row ---- */
.bracket-team {
    display: flex;
    align-items: center;
    padding: 5px 8px;
    font-size: 12px;
    line-height: 1.3;
    gap: 6px;
    border-bottom: 1px solid #2d3239;
    min-height: 28px;
    position: relative;
}
.bracket-team:last-child {
    border-bottom: none;
}

/* Winner highlight */
.bracket-team--winner {
    background: rgba(34,197,94,0.08);
}
.bracket-team--winner .bracket-team-name {
    color: #22c55e;
    font-weight: 700;
}

/* Loser dimming */
.bracket-team--loser .bracket-team-name {
    color: #64748b;
}

/* Seed badge */
.bracket-seed {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 18px;
    font-size: 10px;
    font-weight: 700;
    color: #94a3b8;
    background: #181b1f;
    border-radius: 3px;
    flex-shrink: 0;
    text-align: center;
}

.bracket-team-name {
    flex: 1 1 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 11.5px;
    color: #cbd5e1;
}

/* Win probability */
.bracket-prob {
    font-size: 10px;
    color: #64748b;
    flex-shrink: 0;
    margin-left: auto;
    padding-left: 4px;
}
.bracket-team--winner .bracket-prob {
    color: #4ade80;
}

/* Contrarian dot */
.bracket-contrarian-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #f97316;
    flex-shrink: 0;
    margin-left: 2px;
    title: "Contrarian pick";
}

/* ---- Connector Lines ---- */
.bracket-connector-col {
    display: flex;
    flex-direction: column;
    justify-content: space-around;
    width: 18px;
    position: relative;
    flex-shrink: 0;
}

.bracket-connector {
    position: relative;
    flex: 1 1 0;
    display: flex;
    align-items: center;
}

.bracket-connector-line {
    position: absolute;
    border-color: #3b4252;
    border-style: solid;
}

/* ---- Final Four / Championship ---- */
.bracket-ff-label {
    font-size: 16px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: #f8fafc;
    text-align: center;
    margin-bottom: 4px;
}

.bracket-champ-label {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #94a3b8;
    text-align: center;
}

.bracket-champion-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 12px 16px;
    background: linear-gradient(135deg, rgba(234,179,8,0.15) 0%, #22262b 70%);
    border: 2px solid #eab308;
    border-radius: 8px;
    gap: 4px;
    min-width: 180px;
}
.bracket-champion-card .bracket-champion-name {
    font-size: 16px;
    font-weight: 800;
    color: #fbbf24;
}
.bracket-champion-card .bracket-champion-seed {
    font-size: 12px;
    color: #94a3b8;
}
.bracket-champion-card .bracket-champion-prob {
    font-size: 11px;
    color: #64748b;
}

/* Trophy icon (CSS-only) */
.bracket-trophy {
    font-size: 28px;
    line-height: 1;
    margin-bottom: 2px;
}

/* ---- Responsive ---- */
@media (max-width: 1200px) {
    .bracket-round { min-width: 155px; }
    .bracket-matchup { min-width: 148px; }
    .bracket-team-name { font-size: 10.5px; }
}
@media (max-width: 768px) {
    .bracket-container { padding: 12px 4px; }
    .bracket-round { min-width: 140px; }
    .bracket-matchup { min-width: 134px; }
}
`;
        document.head.appendChild(style);
    }

    // ------------------------------------------------------------------
    // Constants
    // ------------------------------------------------------------------
    const LEFT_REGIONS  = ['South', 'East'];
    const RIGHT_REGIONS = ['West', 'Midwest'];
    const REGION_ROUNDS = [1, 2, 3, 4];          // R64, R32, S16, E8
    const ROUND_LABELS  = {
        1: 'Round of 64',
        2: 'Round of 32',
        3: 'Sweet 16',
        4: 'Elite Eight',
        5: 'Final Four',
        6: 'Championship'
    };
    const GAMES_PER_ROUND = { 1: 16, 2: 8, 3: 4, 4: 2 };

    // ------------------------------------------------------------------
    // Data Helpers
    // ------------------------------------------------------------------

    /**
     * Organize a flat pick array into a nested map:
     *   { region: { round: [picks sorted by game] } }
     */
    function organizePicks(picks) {
        const map = {};
        for (const p of picks) {
            const region = p.region || 'Unknown';
            const round  = p.round;
            if (!map[region]) map[region] = {};
            if (!map[region][round]) map[region][round] = [];
            map[region][round].push(p);
        }
        // Sort each round's games by game number
        for (const region of Object.keys(map)) {
            for (const round of Object.keys(map[region])) {
                map[region][round].sort((a, b) => a.game - b.game);
            }
        }
        return map;
    }

    // ------------------------------------------------------------------
    // DOM Builders
    // ------------------------------------------------------------------

    function el(tag, classes, attrs) {
        const node = document.createElement(tag);
        if (classes) {
            const list = Array.isArray(classes) ? classes : classes.split(' ');
            list.forEach(c => { if (c) node.classList.add(c); });
        }
        if (attrs) {
            for (const [k, v] of Object.entries(attrs)) {
                if (k === 'textContent') node.textContent = v;
                else if (k === 'innerHTML') node.innerHTML = v;
                else if (k === 'title') node.title = v;
                else node.setAttribute(k, v);
            }
        }
        return node;
    }

    /**
     * Build a single matchup card.
     */
    function buildMatchup(pick) {
        if (!pick) return el('div', 'bracket-matchup');

        const card = el('div', 'bracket-matchup');

        // Determine states
        const hasWinner  = !!pick.winner;
        const isUpset    = !!pick.is_upset;
        const isCorrect  = pick.is_correct === true;
        const isWrong    = pick.is_correct === false;

        if (hasWinner && isUpset) {
            card.classList.add('bracket-matchup--upset');
        } else if (hasWinner) {
            card.classList.add('bracket-matchup--has-winner');
        }
        if (isCorrect)  card.classList.add('bracket-matchup--correct');
        if (isWrong)    card.classList.add('bracket-matchup--incorrect');

        // Team A row
        card.appendChild(buildTeamRow(
            pick.team_a, pick.seed_a, pick.winner, pick.win_prob,
            pick.is_contrarian, pick.team_b
        ));
        // Team B row
        card.appendChild(buildTeamRow(
            pick.team_b, pick.seed_b, pick.winner, pick.win_prob,
            pick.is_contrarian, pick.team_a
        ));

        // Tooltip with extra info
        const parts = [];
        if (pick.region && pick.round) {
            parts.push(`${pick.region} - ${ROUND_LABELS[pick.round] || 'R' + pick.round}`);
        }
        if (pick.winner) parts.push(`Pick: ${pick.winner}`);
        if (pick.win_prob != null) parts.push(`Prob: ${(pick.win_prob * 100).toFixed(1)}%`);
        if (pick.actual_winner) parts.push(`Actual: ${pick.actual_winner}`);
        if (isUpset) parts.push('UPSET');
        card.title = parts.join('\n');

        return card;
    }

    function buildTeamRow(teamName, seed, winner, winProb, isContrarian, opponent) {
        if (!teamName) {
            const row = el('div', 'bracket-team');
            row.appendChild(el('span', 'bracket-seed', { textContent: '-' }));
            row.appendChild(el('span', 'bracket-team-name', { textContent: 'TBD' }));
            return row;
        }

        const isWinner = winner && teamName === winner;
        const isLoser  = winner && teamName !== winner;

        const row = el('div', ['bracket-team',
            isWinner ? 'bracket-team--winner' : '',
            isLoser  ? 'bracket-team--loser'  : ''
        ].filter(Boolean));

        // Seed badge
        const seedBadge = el('span', 'bracket-seed', {
            textContent: seed != null ? String(seed) : '?'
        });
        row.appendChild(seedBadge);

        // Team name
        const name = el('span', 'bracket-team-name', { textContent: teamName });
        row.appendChild(name);

        // Win probability (shown only on the winner row)
        if (isWinner && winProb != null) {
            const prob = el('span', 'bracket-prob', {
                textContent: (winProb * 100).toFixed(0) + '%'
            });
            row.appendChild(prob);
        }

        // Contrarian dot (only on the winner row)
        if (isWinner && isContrarian) {
            const dot = el('span', 'bracket-contrarian-dot', { title: 'Contrarian pick' });
            row.appendChild(dot);
        }

        return row;
    }

    /**
     * Build a connector column (the lines between two rounds).
     * For N matchups in the current round, draw N/2 connector pairs that
     * merge two adjacent games into one feed for the next round.
     */
    function buildConnectorCol(matchupCount, roundHeight, side) {
        const col = el('div', 'bracket-connector-col');
        // We use pure CSS borders drawn on wrapper divs
        // Each pair of matchups joins into one line
        const pairs = Math.floor(matchupCount / 2);
        for (let i = 0; i < pairs; i++) {
            const pair = el('div', 'bracket-connector');
            // Top half-bracket
            const top = el('div', 'bracket-connector-line');
            const bot = el('div', 'bracket-connector-line');

            if (side === 'left') {
                top.style.cssText = 'top:25%;bottom:50%;right:0;width:50%;border-right:2px solid #3b4252;border-top:2px solid #3b4252;border-radius:0 5px 0 0;';
                bot.style.cssText = 'top:50%;bottom:25%;right:0;width:50%;border-right:2px solid #3b4252;border-bottom:2px solid #3b4252;border-radius:0 0 5px 0;';
            } else {
                top.style.cssText = 'top:25%;bottom:50%;left:0;width:50%;border-left:2px solid #3b4252;border-top:2px solid #3b4252;border-radius:5px 0 0 0;';
                bot.style.cssText = 'top:50%;bottom:25%;left:0;width:50%;border-left:2px solid #3b4252;border-bottom:2px solid #3b4252;border-radius:0 0 0 5px;';
            }

            pair.appendChild(top);
            pair.appendChild(bot);
            col.appendChild(pair);
        }
        return col;
    }

    /**
     * Build one region (4 rounds of matchups with connectors between).
     * @param {string} regionName
     * @param {object} regionData - { round: [picks] }
     * @param {string} side - 'left' or 'right'
     */
    function buildRegion(regionName, regionData, side) {
        const region = el('div', [
            'bracket-region',
            side === 'right' ? 'bracket-region--right' : ''
        ].filter(Boolean));

        const roundOrder = side === 'left'
            ? [1, 2, 3, 4]
            : [1, 2, 3, 4];  // HTML order; CSS reverses for right

        for (let ri = 0; ri < roundOrder.length; ri++) {
            const roundNum = roundOrder[ri];
            const picks = (regionData && regionData[roundNum]) || [];
            const expected = GAMES_PER_ROUND[roundNum] || 0;

            // Build round column
            const roundCol = el('div', 'bracket-round');
            // Round label on first round only
            if (roundNum === 1) {
                const label = el('div', 'bracket-region-label', { textContent: regionName });
                roundCol.appendChild(label);
            }

            for (let g = 0; g < Math.max(expected, picks.length); g++) {
                roundCol.appendChild(buildMatchup(picks[g] || null));
            }
            region.appendChild(roundCol);

            // Connector between rounds (not after the last round)
            if (ri < roundOrder.length - 1) {
                const gamesInRound = Math.max(expected, picks.length);
                region.appendChild(buildConnectorCol(gamesInRound, 0, side));
            }
        }

        return region;
    }

    /**
     * Build the center column: Final Four + Championship + Champion.
     */
    function buildCenter(pickMap) {
        const center = el('div', 'bracket-center');

        // Final Four label
        center.appendChild(el('div', 'bracket-ff-label', { textContent: 'Final Four' }));

        // Final Four games (round 5)
        const ffPicks = (pickMap['Final Four'] && pickMap['Final Four'][5]) || [];
        const ffRound = el('div', 'bracket-round');
        ffRound.style.cssText = 'min-width:200px;gap:16px;';
        for (let i = 0; i < Math.max(2, ffPicks.length); i++) {
            ffRound.appendChild(buildMatchup(ffPicks[i] || null));
        }
        center.appendChild(ffRound);

        // Championship label
        center.appendChild(el('div', 'bracket-champ-label', { textContent: 'Championship' }));

        // Championship game (round 6)
        const champPicks = (pickMap['Championship'] && pickMap['Championship'][6]) || [];
        if (champPicks.length > 0) {
            center.appendChild(buildMatchup(champPicks[0]));
        } else {
            center.appendChild(buildMatchup(null));
        }

        // Champion display
        const champGame = champPicks[0];
        if (champGame && champGame.winner) {
            const card = el('div', 'bracket-champion-card');
            card.appendChild(el('div', 'bracket-trophy', { textContent: '\u{1F3C6}' }));
            card.appendChild(el('div', 'bracket-champion-name', {
                textContent: champGame.winner
            }));
            const winnerSeed = champGame.winner === champGame.team_a
                ? champGame.seed_a : champGame.seed_b;
            if (winnerSeed != null) {
                card.appendChild(el('div', 'bracket-champion-seed', {
                    textContent: '#' + winnerSeed + ' Seed'
                }));
            }
            if (champGame.win_prob != null) {
                card.appendChild(el('div', 'bracket-champion-prob', {
                    textContent: (champGame.win_prob * 100).toFixed(1) + '% win probability'
                }));
            }
            center.appendChild(card);
        }

        return center;
    }

    // ------------------------------------------------------------------
    // Region Assignment Helpers
    // ------------------------------------------------------------------

    /**
     * Determine which regions to place on the left and right halves.
     * We attempt to honour the standard bracket layout. If the data has
     * different region names we fall back to alphabetical splitting.
     */
    function assignHalves(regionNames) {
        const left  = [];
        const right = [];

        for (const name of regionNames) {
            if (LEFT_REGIONS.includes(name)) {
                left.push(name);
            } else if (RIGHT_REGIONS.includes(name)) {
                right.push(name);
            }
        }

        // If the standard names did not cover all regions, distribute extras
        const assigned = new Set([...left, ...right]);
        const extras = regionNames.filter(r => !assigned.has(r));
        for (const name of extras) {
            if (left.length <= right.length) left.push(name);
            else right.push(name);
        }

        return { left, right };
    }

    // ------------------------------------------------------------------
    // Public API
    // ------------------------------------------------------------------

    /**
     * Render a full NCAA tournament bracket into the given container.
     *
     * @param {Array} picks  - Array of pick objects from the API.
     * @param {HTMLElement} container - DOM element to render into.
     */
    function renderBracketViz(picks, container) {
        if (!container) {
            console.error('[bracket_viz] No container element provided.');
            return;
        }
        if (!Array.isArray(picks) || picks.length === 0) {
            container.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">' +
                'No bracket data available.</div>';
            return;
        }

        // 1. Inject CSS
        injectStyles();

        // 2. Clear container
        container.innerHTML = '';

        // 3. Organize picks
        const pickMap = organizePicks(picks);

        // 4. Determine regions (exclude meta-regions)
        const metaRegions = new Set(['Final Four', 'Championship']);
        const regionNames = Object.keys(pickMap).filter(r => !metaRegions.has(r));
        const { left, right } = assignHalves(regionNames);

        // 5. Build bracket DOM
        const wrapper = el('div', 'bracket-container');

        // Left half
        const leftHalf = el('div', 'bracket-half bracket-half--left');
        for (const regionName of left) {
            leftHalf.appendChild(buildRegion(regionName, pickMap[regionName], 'left'));
        }
        wrapper.appendChild(leftHalf);

        // Center
        wrapper.appendChild(buildCenter(pickMap));

        // Right half
        const rightHalf = el('div', 'bracket-half bracket-half--right');
        for (const regionName of right) {
            rightHalf.appendChild(buildRegion(regionName, pickMap[regionName], 'right'));
        }
        wrapper.appendChild(rightHalf);

        // 6. Append
        container.appendChild(wrapper);
    }

    // ------------------------------------------------------------------
    // Export
    // ------------------------------------------------------------------
    // Attach to window for global access (no module bundler assumed)
    window.renderBracketViz = renderBracketViz;

})();
