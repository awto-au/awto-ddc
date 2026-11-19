#include <stdint.h>
#include <string.h>
#include "UserCommonInclude.h"
#if(_AWTO_SAVER_ASTEROIDS == _ON)                                        // saver not in the image when _OFF (RL6449_Project.h)
#include "../../tools/osd_lines/osd_lines.h"

// Asteroids screensaver (docs/asteroids.md): the game runs on the chip (rocks split, shots, saucer, autopilot ship, wrap-around),
// drawn like Scope 2: 30 x 11 tiles of 12 x 18 (360 x 198), 1-bit glyphs, one-tile-column band canvas of saver_canvas.c,
// objects culled per pass; only the tiles under objects that moved / changed are redrawn and uploaded (docs/saver-fps-plan.md). Game ticks at column 0.
//   AwtoAsteroids(1) draw   (2) next column, returns 1 when a frame is complete   (0) off
// Shapes: asteroids_data.inc (scripts/gen_asteroids.py: local ROM geometry or own outlines; gitignored).
extern __xdata uint8_t g_aucScPix[];
extern __xdata uint8_t g_aucScDirty[];
extern __xdata osd_canvas g_scCv;
extern void AwtoScTile(WORD usAddr, BYTE __xdata *pucB);                          // direct data port stores (saver_canvas.c)
#define AWTO_AST_TILE(c, p)                     AwtoScTile(AWTO_AST_ROWS + 1 + AWTO_AST_COLS * AWTO_AST_ROWS + (OSD_TILE_BYTES / 3) * ((g_ucAwtoOsdRot != 0) ? AwtoOsdRotCell((c), AWTO_AST_COLS * AWTO_AST_ROWS) : (c)), (p))
#include "asteroids_data.inc"

#ifndef AWTO_AST_COLS
#define AWTO_AST_COLS                           30                                  // canvas size variants (-D, docs/asteroids-resolution.md): ids = cells <= 512 on the hardware map
#endif
#ifndef AWTO_AST_ROWS
#define AWTO_AST_ROWS                           11
#endif
#ifndef AWTO_AST_RES
#define AWTO_AST_RES                            0                                   // 1 = objects 2 x larger in px (finer pixels at the same screen size): shape shifts and radii only
#endif
#define AWTO_AST_TW                             OSD_TILE_W
#define AWTO_AST_TH                             OSD_TILE_H
#define AWTO_AST_W                              (AWTO_AST_COLS * AWTO_AST_TW)
#define AWTO_AST_H                              (AWTO_AST_ROWS * AWTO_AST_TH)
#define AWTO_AST_BAND_ROWS                      6                                   // canvas rows = the tallest band (the line walker's byte window: 6 rows + 64 px margins)
#define AWTO_AST_BANDS                          ((AWTO_AST_ROWS + AWTO_AST_BAND_ROWS - 1) / AWTO_AST_BAND_ROWS)   // 11 rows: 6 + 5
#define AWTO_AST_WIDE                           ((AWTO_AST_W > 360) || (AWTO_AST_H > 198))   // coordinates beyond a byte after the + one playfield
#if(AWTO_AST_WIDE)
typedef WORD AstY;
#else
typedef BYTE AstY;
#endif
#define AWTO_AST_BAND_H                         (AWTO_AST_BAND_ROWS * AWTO_AST_TH)
#define AWTO_AST_BG                             AWTO_PAL_DIAG_BG                    // palette indexes: the diagnostic console's (text 1, background 3; the console sets them again when it opens)
#define AWTO_AST_FG                             AWTO_PAL_DIAG_TEXT
#define AWTO_AST_FG_SHIFT                       4
#define AWTO_AST_BG_R                           2
#define AWTO_AST_BG_G                           2
#define AWTO_AST_BG_B                           6
#define AWTO_AST_SCALE_64                       64                                  // scale-up factor unit: ratio = 64 / factor
#define AWTO_AST_SCALED_W                       (AWTO_AST_SCALE_64 * (long)AWTO_AST_W)
#define AWTO_AST_SCALED_H                       (AWTO_AST_SCALE_64 * (long)AWTO_AST_H)
#define AWTO_AST_SU_FACTOR                      ((BYTE)(AWTO_AST_SCALED_W / _PANEL_DH_WIDTH))   // the width fills the panel exactly
#define AWTO_AST_POS_H                          ((BYTE)((_PANEL_DH_WIDTH - AWTO_AST_SCALED_W / AWTO_AST_SU_FACTOR) / 2 / AWTO_OSD_PX_PER_HD))
#define AWTO_AST_POS_V                          ((BYTE)((_PANEL_DV_HEIGHT - AWTO_AST_SCALED_H / AWTO_AST_SU_FACTOR) / 2))   // equal bars top and bottom: Rotate 180 keeps the picture in place
#ifndef AWTO_AST_ODD_BAR_OK
#define AWTO_AST_ODD_BAR_OK                     0                                   // 1 (variant builds): an odd bar pair is accepted, Rotate 180 then moves the picture 1 px (35 x 13: bars 21 + 20 px)
#endif
typedef char s_tAstPanelCheck[((AWTO_AST_SU_FACTOR * (long)_PANEL_DH_WIDTH == AWTO_AST_SCALED_W) && (AWTO_AST_SCALED_H / AWTO_AST_SU_FACTOR <= _PANEL_DV_HEIGHT) &&
                               (((_PANEL_DV_HEIGHT - AWTO_AST_SCALED_H / AWTO_AST_SU_FACTOR) % 2) == 0 || AWTO_AST_ODD_BAR_OK)) ? 1 : -1];   // full width, height inside the panel, even bars
#define AWTO_AST_ARG_ON                         0x90                                // sync E9 (no rows: the table is full): value = shape source (AWTO_AST_FROM_ROM)
#define AWTO_AST_ARG_FRAME                      0x91
#define AWTO_AST_ARG_OFF                        0x92

// game units: 1/8 px
#define AWTO_AST_FP                             3
#define AWTO_AST_FPW                            (AWTO_AST_W << AWTO_AST_FP)
#define AWTO_AST_FPH                            (AWTO_AST_H << AWTO_AST_FP)
#define AWTO_AST_N_OBJ                          24
#define AWTO_AST_TICK_MS                        126                                 // game tick period: 1000 / 126 = 7.94 ticks/s (the pace of the first version, 7.96 measured: docs/asteroids.md)
#define AWTO_AST_TICKS                          2                                   // ticks per frame at the first version's pace: flame blink and frame sync number count in these
#define AWTO_AST_HALF_MS                        0x8000                              // WORD ms difference below this = the time has passed
#define AWTO_AST_MAX_CATCHUP                    4                                   // ticks run in one frame at most; further behind = resync (a long pass is not made up in a burst)
#define AWTO_AST_SEED                           0x2F6B
#define AWTO_AST_T_NONE                         0
#define AWTO_AST_T_ROCK_L                       1                                   // rocks L / M / S, saucers L / S: consecutive
#define AWTO_AST_T_ROCK_M                       2
#define AWTO_AST_T_ROCK_S                       3
#define AWTO_AST_T_SAUCER_L                     4
#define AWTO_AST_T_SAUCER_S                     5
#define AWTO_AST_T_SHOT                         6
#define AWTO_AST_T_SSHOT                        7
#define AWTO_AST_T_BOOM                         8                                   // aux = age, cVx = size (px)
#define AWTO_AST_N_TYPES                        9
#define AWTO_AST_SHAPES_PER_ROCK                4
#define AWTO_AST_SHIFT_ROCK_L                   (1 - AWTO_AST_RES)                                  // shape units >> shift = px: rock 64 -> 32 / 16 / 8 px
#define AWTO_AST_SHIFT_SAUCER_L                 (2 - AWTO_AST_RES)
#define AWTO_AST_SHIFT_SAUCER_S                 (3 - AWTO_AST_RES)
#define AWTO_AST_SHIFT_SHIP                     (3 - AWTO_AST_RES)                                  // hull tip radius 56 -> 7 px
#define AWTO_AST_ANGLES                         64                                  // ship heading steps, 0 = right, counter-clockwise
#define AWTO_AST_QUARTER                        16
#define AWTO_AST_UP                             16
#define AWTO_AST_RAD_ROCK_L                     (17 << AWTO_AST_RES)                                 // large rock draw radius, px (64 units >> 1 = 32 px wide); smaller sizes halve
#define AWTO_AST_RAD_SAUCER_L                   (11 << AWTO_AST_RES)
#define AWTO_AST_SHIP_R                         (9 << AWTO_AST_RES)                                  // draw radius, px
#define AWTO_AST_SHIP_HIT                       (5 << AWTO_AST_RES)
#define AWTO_AST_SHOT_SPEED                     48                                  // fp units per step
#define AWTO_AST_SSHOT_SPEED                    36
#define AWTO_AST_SHOT_TTL                       15
#define AWTO_AST_SSHOT_TTL                      20
#define AWTO_AST_SHOTS_MAX                      4
#define AWTO_AST_FIRE_CD                        3
#define AWTO_AST_TIP                            56                                  // muzzle distance from the ship centre, fp
#define AWTO_AST_ACC                            2
#define AWTO_AST_VMAX                           20
#define AWTO_AST_DRAG_MASK                      3
#define AWTO_AST_TURN_FAST                      40                                  // |cross| above dist * this (about 18 deg off): two heading steps
#define AWTO_AST_AIM_TOL                        9                                   // fire below dist * this (about 4 deg)
#define AWTO_AST_RANGE                          720                                 // fire only within 90 px (fp)
#define AWTO_AST_DANGER                         288                                 // 36 px
#define AWTO_AST_LEAD_SHIFT                     5
#define AWTO_AST_THRUST_STEPS                   6
#define AWTO_AST_WANDER_MASK                    31
#define AWTO_AST_LIVES                          3
#define AWTO_AST_RESPAWN_STEPS                  24
#define AWTO_AST_CLEAR_PX                       48                                  // centre must be free of objects within this to respawn
#define AWTO_AST_OVER_STEPS                     60
#define AWTO_AST_WAVE_STEPS                     24
#define AWTO_AST_WAVE_ROCKS                     4
#define AWTO_AST_WAVE_ROCKS_MAX                 7
#define AWTO_AST_EDGE_PX                        80                                  // wave rocks start within this of the left / right edge
#define AWTO_AST_BOOM_LIFE                      12
#define AWTO_AST_BOOM_SHIP_LIFE                 22
#define AWTO_AST_BOOM_BIG                       (17 << AWTO_AST_RES)                                 // boom size above this = the ship's (longer life)
#define AWTO_AST_BOOM_SHIP_SIZE                 (20 << AWTO_AST_RES)
#define AWTO_AST_BOOM_DOTS                      8
#define AWTO_AST_BOOM_STEP                      8                                   // heading steps between dashes (64 / 8)
#define AWTO_AST_SAUCER_MIN                     150                                 // steps until the next saucer: min + rnd % range
#define AWTO_AST_SAUCER_RANGE                   200
#define AWTO_AST_SAUCER_VX                      10
#define AWTO_AST_SAUCER_VX_S                    14
#define AWTO_AST_SAUCER_VY                      8
#define AWTO_AST_SAUCER_FIRE                    22
#define AWTO_AST_SAUCER_MARGIN                  20                                  // px from the top / bottom at entry
#define AWTO_AST_SAUCER_SMALL_PCT               25
#define AWTO_AST_SCORE_ROCK_L                   20
#define AWTO_AST_SCORE_ROCK_M                   50
#define AWTO_AST_SCORE_ROCK_S                   100
#define AWTO_AST_SCORE_SAUCER_L                 200
#define AWTO_AST_SCORE_SAUCER_S                 1000
#define AWTO_AST_DIGITS                         5
#define AWTO_AST_HUD_X                          8
#define AWTO_AST_HUD_BASE                       18                                  // score baseline
#define AWTO_AST_DIGIT_ADV                      12
#define AWTO_AST_LIFE_X                         14
#define AWTO_AST_LIFE_Y                         34
#define AWTO_AST_LIFE_ADV                       12
#define AWTO_AST_HUD_W                          (AWTO_AST_HUD_X + AWTO_AST_DIGITS * AWTO_AST_DIGIT_ADV)
#define AWTO_AST_HUD_H                          44
#define AWTO_AST_DEC                            10
#ifndef AWTO_SAVER_INFO
#define AWTO_SAVER_INFO                         _ON                                 // info overlay (docs/saver-mode.md "Info overlay"); _OFF = none, no code
#endif
#define AWTO_AST_CH_X                           10                                  // info glyphs after the digits (scripts/gen_asteroids.py DIGITS order)
#define AWTO_AST_CH_DOT                         11
#define AWTO_AST_CH_F                           12
#define AWTO_AST_CH_P                           13
#define AWTO_AST_CH_S                           14
#define AWTO_AST_CH_SPACE                       0xFF
#define AWTO_AST_INFO_COL0                      0                                   // corner: lower left of the picture (first column; the tile map is turned by Rotate 180 with the game)
#define AWTO_AST_INFO_ROWS                      2                                   // tile rows, the last ones of the field
#define AWTO_AST_INFO_ROW0                      (AWTO_AST_ROWS - AWTO_AST_INFO_ROWS)
#define AWTO_AST_INFO_LINES                     3                                   // input + refresh / draw grid + scale / frames per second
#define AWTO_AST_INFO_CHARS                     16
#define AWTO_AST_INFO_SHIFT                     1                                   // digit shapes 8 x 12 >> 1 = 4 x 6 px
#define AWTO_AST_INFO_ADV                       6
#define AWTO_AST_INFO_GH                        6                                   // glyph height px (12 >> shift)
#define AWTO_AST_INFO_GW                        4
#define AWTO_AST_INFO_X                         3                                   // px from the column edge
#define AWTO_AST_INFO_BASE0                     12                                  // first baseline below the top of the info rows
#define AWTO_AST_INFO_LINE_STEP                 8
#define AWTO_AST_INFO_COLS                      ((AWTO_AST_INFO_X + AWTO_AST_INFO_CHARS * AWTO_AST_INFO_ADV + AWTO_AST_TW - 1) / AWTO_AST_TW)
#define AWTO_AST_INFO_Y                         ((AWTO_AST_INFO_ROW0 - AWTO_AST_BAND_ROWS) * AWTO_AST_TH)   // top of the info rows in the band-1 canvas
#define AWTO_AST_INFO_FPS_CHARS                 7                                   // `NNN FPS`
#define AWTO_AST_INFO_FPS_COLS                  ((AWTO_AST_INFO_X + AWTO_AST_INFO_FPS_CHARS * AWTO_AST_INFO_ADV + AWTO_AST_TW - 1) / AWTO_AST_TW)
#define AWTO_AST_INFO_FPS_BITS                  (1 << (AWTO_AST_INFO_ROWS - 1))     // the fps line sits in the last info tile row
typedef char s_tAstInfoFpsCheck[(AWTO_AST_INFO_BASE0 + (AWTO_AST_INFO_LINES - 1) * AWTO_AST_INFO_LINE_STEP - AWTO_AST_INFO_GH >= (AWTO_AST_INFO_ROWS - 1) * AWTO_AST_TH) ? 1 : -1];   // line 3's glyph top is inside the last row
#define AWTO_AST_INFO_BITS                      ((1 << AWTO_AST_INFO_ROWS) - 1)
#define AWTO_AST_INFO_PERIOD_MS                 1000                                // numbers refresh once a second: the fps count is per this period
#define AWTO_AST_INFO_TENTHS                    10
#define AWTO_AST_DEC_TOP                        10000                               // WORD values: 5 digits
#define AWTO_AST_INFO_DEC_DIGITS                5
#define AWTO_AST_INFO_SCALE_TENTHS              ((WORD)((AWTO_AST_SCALE_64 * AWTO_AST_INFO_TENTHS + AWTO_AST_SU_FACTOR / 2) / AWTO_AST_SU_FACTOR))   // scale-up factor x 10
#define AWTO_AST_INFO_WORD_BITS                 16
#define AWTO_AST_THOUSAND                       1000
#define AWTO_AST_INFO_VF_UNIT_MHZ               100                                 // SDK vertical frequency unit 0.1 Hz = 100 mHz
typedef char s_tAstShapesCheck[(AWTO_AST_N_SHAPES == AWTO_AST_SH_DIGIT + AWTO_AST_DEC + 5) ? 1 : -1];   // digits then the five info glyphs
typedef char s_tAstInfoCheck[((AWTO_AST_INFO_ROW0 >= AWTO_AST_BAND_ROWS) && (AWTO_AST_INFO_LINE_STEP * AWTO_AST_INFO_LINES + AWTO_AST_INFO_BASE0 <= AWTO_AST_INFO_ROWS * AWTO_AST_TH)) ? 1 : -1];   // rows inside band 1, text inside them
#define AWTO_AST_PASSES                         (AWTO_AST_COLS * AWTO_AST_BANDS)
#define AWTO_AST_PASS_MS                        8                                   // saver work per call (+ one column): the main loop (DDC/CI, keys) runs between calls
#define AWTO_AST_FRAME_MS                       40                                  // frame schedule: 25 frames/s; game ticks stay at AWTO_AST_TICK_MS, positions interpolated
#define AWTO_AST_FRAC_BITS                      3                                   // interpolation step: 1/8 of a tick
#define AWTO_AST_FRAC_MAX                       ((1 << AWTO_AST_FRAC_BITS) - 1)
#define AWTO_AST_SHIP_SLOT                      AWTO_AST_N_OBJ                      // s_atSeen: objects, then the ship
#define AWTO_AST_KEY_SUBS                       24                                  // draw key = type * this + shape / age (boom life 22 < 24; 8 * 24 + 23 fits a byte)
#define AWTO_AST_FLAME_KEY                      0x40                                // ship key: heading (6 bits) | flame
#define AWTO_AST_DIV_TW_SHIFT                   2                                   // x / 12 = (x >> 2) / 3: byte divides only
#define AWTO_AST_DIV_TW_REST                    (AWTO_AST_TW >> AWTO_AST_DIV_TW_SHIFT)
#define AWTO_AST_DIV_TH_SHIFT                   1                                   // y / 18 = (y >> 1) / 9
#define AWTO_AST_DIV_TH_REST                    (AWTO_AST_TH >> AWTO_AST_DIV_TH_SHIFT)
#define AWTO_AST_HUD_COLS                       ((AWTO_AST_HUD_W + AWTO_AST_TW - 1) / AWTO_AST_TW)
#define AWTO_AST_HUD_ROWS                       ((AWTO_AST_HUD_H + AWTO_AST_TH - 1) / AWTO_AST_TH)
#define AWTO_AST_BYTE_BITS                      3
#define AWTO_AST_BIT_MASK                       7
#define AWTO_AST_MUL_TW(v)                      ((BYTE)((BYTE)((v) << 3) + (BYTE)((v) << 2)))   // v * 12 (tile width, checked below) without a multiply
#define AWTO_AST_STATE_ALIVE                    0
#define AWTO_AST_STATE_DEAD                     1                                   // waiting to respawn
#define AWTO_AST_STATE_OVER                     2
#define AWTO_AST_NONE                           0xFF

// sound: cmds of AwtoPmSound (snd.c)
#define AWTO_AST_SND_FIRE                       9
#define AWTO_AST_SND_BOOM_S                     10
#define AWTO_AST_SND_BOOM_M                     11
#define AWTO_AST_SND_BOOM_L                     12
#define AWTO_AST_SND_BOOM_SHIP                  13
#define AWTO_AST_SND_STOP                       4
#define AWTO_AST_BG_NONE                        0
#define AWTO_AST_BG_THRUST                      5
#define AWTO_AST_BG_SAUCER                      6

typedef struct
{
    int16_t sX;
    int16_t sY;
    int8_t cVx;
    int8_t cVy;
    BYTE ucType;
    BYTE ucAux;                                                                     // rock: shape; shots: ttl; saucer: fire timer; boom: age
} AstObj;

typedef struct                                                                      // an object as drawn (docs/saver-fps-plan.md: incremental redraw)
{
    int16_t sX;                                                                     // centre, playfield px
    AstY ucY;
    BYTE ucR;                                                                       // draw radius (AstRad); 0 = nothing drawn
    BYTE ucKey;                                                                     // shape / heading / age: a change redraws
} AstSeen;

__xdata WORD g_usAwtoAstStep;                                                       // game steps (also read by scripts/asteroids_speed.py)
__xdata BYTE g_ucAwtoAstCol;                                                        // next column of the frame being drawn
#ifdef _AWTO_OSD_HWTEST
__xdata WORD g_usAwtoAstFrames;
#elif(AWTO_SAVER_INFO == _ON)
__xdata BYTE g_usAwtoAstFrames;                                                     // low byte is enough for the per-second count
#endif
static __xdata AstObj s_atObj[AWTO_AST_N_OBJ];
static __xdata AstSeen s_atSeen[AWTO_AST_N_OBJ + 1];                                // last frame as drawn: objects, then the ship
static __xdata AstSeen s_tNow;                                                      // this frame, the slot being compared
static __xdata uint8_t s_aucDirty[AWTO_AST_PASSES];                                 // per pass: bit n = tile row n of the band changes this frame
static __xdata int16_t s_sLx0;                                                      // AstLine endpoints, canvas px
static __xdata int16_t s_sLy0;
static __xdata int16_t s_sLx1;
static __xdata int16_t s_sLy1;
static __xdata uint8_t s_aucDig[AWTO_AST_DIGITS];
static __xdata WORD s_usRng;
static __xdata WORD s_usScore;
static __xdata int16_t s_sShX;
static __xdata int16_t s_sShY;
static __xdata int8_t s_cShVx;
static __xdata int8_t s_cShVy;
static __xdata BYTE s_ucShAng;
static __xdata BYTE s_ucShState;
static __xdata BYTE s_ucShTimer;
static __xdata BYTE s_ucShCd;
static __xdata BYTE s_ucShThrust;
static __xdata BYTE s_ucThrustLeft;
static __xdata BYTE s_ucLives;
static __xdata BYTE s_ucWave;
static __xdata BYTE s_ucWaveTimer;
static __xdata WORD s_usSaucerTimer;
static __xdata BYTE s_ucShown;
static __xdata WORD s_usTickAt;                                                     // scheduled time of the next game tick (AwtoMs low word); advances by the period, never restarts from now
static __xdata WORD s_usFrameAt;                                                    // scheduled start of the next frame
static __xdata BYTE s_ucFrac;                                                       // this frame's time since the last tick, 1/8 ticks
static __xdata BYTE s_ucDigN;
static __xdata int16_t s_sOx;                                                       // origin of the pass being drawn
static __xdata int16_t s_sOy;
static __xdata int16_t s_sRx;                                                       // object centre relative to the pass canvas
static __xdata int16_t s_sRy;
static __xdata int8_t s_cDx;                                                        // AstDir result: 127 * (cos, -sin), screen y down
static __xdata int8_t s_cDy;
static __xdata WORD s_usCell0;
static __xdata WORD s_usHudScore;                                                   // score / lives as last drawn
static __xdata BYTE s_ucHudLives;
static __xdata BYTE s_ucHudDirty;                                                   // they changed: this frame redraws the HUD passes
static __xdata BYTE s_ucBandRows;                                                   // tile rows of the pass being drawn (the last band may be shorter)
static __xdata int16_t s_sBandH;                                                    // clip rows of the pass: s_sClip0 <= y < s_sBandH (canvas px; the changed tiles)
static __xdata int16_t s_sClip0;

#pragma place bank(8)
static __code int8_t s_tCos[AWTO_AST_QUARTER + 1] = {127, 126, 125, 122, 117, 112, 106, 98, 90, 81, 71, 60, 49, 37, 25, 12, 0};
static BYTE AstRad(BYTE ucT)                                                        // draw radius, px (no table: a const chunk near the top of a bank trips the link gate's arithmetic-base heuristic)
{
    switch(ucT)
    {
        case AWTO_AST_T_ROCK_L:
            return AWTO_AST_RAD_ROCK_L;
        case AWTO_AST_T_ROCK_M:
            return AWTO_AST_RAD_ROCK_L / 2 + 1;
        case AWTO_AST_T_ROCK_S:
            return AWTO_AST_RAD_ROCK_L / 4 + 1;
        case AWTO_AST_T_SAUCER_L:
            return AWTO_AST_RAD_SAUCER_L;
        case AWTO_AST_T_SAUCER_S:
            return AWTO_AST_RAD_SAUCER_L / 2 + 1;
        case AWTO_AST_T_SHOT:
        case AWTO_AST_T_SSHOT:
            return 2;
        default:
            return AWTO_AST_BOOM_SHIP_SIZE + 1;
    }
}

static BYTE AstHit(BYTE ucT)                                                        // hit radius, px
{
    switch(ucT)
    {
        case AWTO_AST_T_ROCK_L:
            return AWTO_AST_RAD_ROCK_L - 3;
        case AWTO_AST_T_ROCK_M:
            return AWTO_AST_RAD_ROCK_L / 2 - 1;
        case AWTO_AST_T_ROCK_S:
            return AWTO_AST_RAD_ROCK_L / 4;
        case AWTO_AST_T_SAUCER_L:
            return AWTO_AST_RAD_SAUCER_L - 2;
        case AWTO_AST_T_SAUCER_S:
            return AWTO_AST_RAD_SAUCER_L / 2;
        case AWTO_AST_T_SHOT:
        case AWTO_AST_T_SSHOT:
            return 1;
        default:
            return 0;
    }
}

#pragma place bank(8)
static void AstDir(BYTE ucAng)
{
    BYTE ucQ = (BYTE)((ucAng / AWTO_AST_QUARTER) & 3);
    BYTE ucR = ucAng % AWTO_AST_QUARTER;
    int8_t cC = s_tCos[ucR];
    int8_t cS = s_tCos[AWTO_AST_QUARTER - ucR];

    if(ucQ == 0)
    {
        s_cDx = cC;
        s_cDy = (int8_t)-cS;
    }
    else if(ucQ == 1)
    {
        s_cDx = (int8_t)-cS;
        s_cDy = (int8_t)-cC;
    }
    else if(ucQ == 2)
    {
        s_cDx = (int8_t)-cC;
        s_cDy = cS;
    }
    else
    {
        s_cDx = cS;
        s_cDy = cC;
    }
}

static BYTE AstRnd(void)
{
    s_usRng ^= (WORD)(s_usRng << 7);
    s_usRng ^= (WORD)(s_usRng >> 9);
    s_usRng ^= (WORD)(s_usRng << 8);
    return (BYTE)(s_usRng >> 4);
}

static void AstSnd(BYTE ucCmd)
{
    if(GET_OSD_VOLUME_MUTE() == 0)                                                  // muted by the user: silent (volume = the user's DVC gain)
    {
        AwtoPmSound(ucCmd);
    }
}

static void AstBg(BYTE ucState)
{
    AwtoPmSoundBg((GET_OSD_VOLUME_MUTE() == 0) ? ucState : AWTO_AST_BG_NONE);
}

static void AstPoll(void)                                                           // the sound sequencer is served between drawing steps, not once per 10-40 ms pass (docs/pacman-sound.md "Timing")
{
    AwtoPmSoundPoll();
}

static int16_t AstDiff(int16_t sD, int16_t sM)                                      // shortest signed difference on a ring of sM
{
    if(sD > (sM / 2))
    {
        sD -= sM;
    }
    else if(sD < -(sM / 2))
    {
        sD += sM;
    }
    return sD;
}

static BYTE AstNear(int16_t sAx, int16_t sAy, int16_t sBx, int16_t sBy, BYTE ucSum)    // toroidal distance in px below ucSum
{
    int16_t sDx = AstDiff(sAx - sBx, AWTO_AST_FPW) >> AWTO_AST_FP;
    int16_t sDy = AstDiff(sAy - sBy, AWTO_AST_FPH) >> AWTO_AST_FP;

    if(sDx < 0)
    {
        sDx = -sDx;
    }
    if(sDy < 0)
    {
        sDy = -sDy;
    }
    if((sDx >= ucSum) || (sDy >= ucSum))
    {
        return 0;
    }
    return ((WORD)(sDx * sDx) + (WORD)(sDy * sDy)) < (WORD)((WORD)ucSum * ucSum);
}

static BYTE AstAlloc(void)
{
    BYTE ucI;

    for(ucI = 0; ucI < AWTO_AST_N_OBJ; ucI++)
    {
        if(s_atObj[ucI].ucType == AWTO_AST_T_NONE)
        {
            return ucI;
        }
    }
    return AWTO_AST_NONE;
}

static BYTE AstAdd(BYTE ucType, int16_t sX, int16_t sY, int8_t cVx, int8_t cVy, BYTE ucAux)    // the slot, or AWTO_AST_NONE when the pool is full
{
    BYTE ucI = AstAlloc();

    if(ucI != AWTO_AST_NONE)
    {
        s_atObj[ucI].ucType = ucType;
        s_atObj[ucI].sX = sX;
        s_atObj[ucI].sY = sY;
        s_atObj[ucI].cVx = cVx;
        s_atObj[ucI].cVy = cVy;
        s_atObj[ucI].ucAux = ucAux;
    }
    return ucI;
}

static void AstRockVel(BYTE ucType, BYTE ucSlot)                                    // random heading, speed by size
{
    BYTE ucSpeed = (BYTE)((AstRnd() & 7) + 5 + (ucType - AWTO_AST_T_ROCK_L) * 5);

    AstDir(AstRnd() & (AWTO_AST_ANGLES - 1));
    s_atObj[ucSlot].cVx = (int8_t)(((int16_t)s_cDx * ucSpeed) >> 7);
    s_atObj[ucSlot].cVy = (int8_t)(((int16_t)s_cDy * ucSpeed) >> 7);
}

static void AstBoom(int16_t sX, int16_t sY, BYTE ucSize)
{
    AstAdd(AWTO_AST_T_BOOM, sX, sY, (int8_t)ucSize, 0, 0);
}

static BYTE AstBoomSnd(BYTE ucT)
{
    if(ucT == AWTO_AST_T_ROCK_L)
    {
        return AWTO_AST_SND_BOOM_L;
    }
    return (ucT == AWTO_AST_T_ROCK_S) ? AWTO_AST_SND_BOOM_S : AWTO_AST_SND_BOOM_M;
}

static void AstBreak(BYTE ucI)                                                      // a rock or saucer is destroyed: score, children, boom
{
    BYTE ucT = s_atObj[ucI].ucType;
    int16_t sX = s_atObj[ucI].sX;
    int16_t sY = s_atObj[ucI].sY;
    BYTE ucK;
    BYTE ucS;

    s_atObj[ucI].ucType = AWTO_AST_T_NONE;
    if(ucT == AWTO_AST_T_ROCK_L)
    {
        s_usScore += AWTO_AST_SCORE_ROCK_L;
    }
    else if(ucT == AWTO_AST_T_ROCK_M)
    {
        s_usScore += AWTO_AST_SCORE_ROCK_M;
    }
    else if(ucT == AWTO_AST_T_ROCK_S)
    {
        s_usScore += AWTO_AST_SCORE_ROCK_S;
    }
    else
    {
        s_usScore += (ucT == AWTO_AST_T_SAUCER_L) ? AWTO_AST_SCORE_SAUCER_L : AWTO_AST_SCORE_SAUCER_S;
    }
    if(ucT < AWTO_AST_T_ROCK_S)
    {
        for(ucK = 0; ucK < 2; ucK++)
        {
            ucS = AstAdd(ucT + 1, sX, sY, 0, 0, AstRnd() & (AWTO_AST_SHAPES_PER_ROCK - 1));
            if(ucS != AWTO_AST_NONE)
            {
                AstRockVel(ucT + 1, ucS);
            }
        }
    }
    AstSnd(AstBoomSnd(ucT));
    AstBoom(sX, sY, AstRad(ucT) - 1);
}

static void AstShipDie(void)
{
    AstBoom(s_sShX, s_sShY, AWTO_AST_BOOM_SHIP_SIZE);
    AstSnd(AWTO_AST_SND_BOOM_SHIP);
    s_ucShState = AWTO_AST_STATE_DEAD;
    s_ucShTimer = AWTO_AST_RESPAWN_STEPS;
    s_ucThrustLeft = 0;
    if(s_ucLives != 0)
    {
        s_ucLives--;
    }
    if(s_ucLives == 0)
    {
        s_ucShState = AWTO_AST_STATE_OVER;
        s_ucShTimer = AWTO_AST_OVER_STEPS;
    }
}

static void AstNewWave(void)
{
    BYTE ucN = AWTO_AST_WAVE_ROCKS + s_ucWave;
    BYTE ucK;
    BYTE ucS;
    int16_t sX;

    if(ucN > AWTO_AST_WAVE_ROCKS_MAX)
    {
        ucN = AWTO_AST_WAVE_ROCKS_MAX;
    }
    for(ucK = 0; ucK < ucN; ucK++)
    {
        sX = (int16_t)(AstRnd() % AWTO_AST_EDGE_PX);
        if((AstRnd() & 1) != 0)
        {
            sX = AWTO_AST_W - 1 - sX;
        }
        ucS = AstAdd(AWTO_AST_T_ROCK_L, sX << AWTO_AST_FP, (int16_t)(AstRnd() % AWTO_AST_H) << AWTO_AST_FP, 0, 0, AstRnd() & (AWTO_AST_SHAPES_PER_ROCK - 1));
        if(ucS != AWTO_AST_NONE)
        {
            AstRockVel(AWTO_AST_T_ROCK_L, ucS);
        }
    }
    if(s_ucWave < 0xFF)
    {
        s_ucWave++;
    }
}

static void AstNewGame(void)
{
    BYTE ucI;

    for(ucI = 0; ucI < AWTO_AST_N_OBJ; ucI++)
    {
        s_atObj[ucI].ucType = AWTO_AST_T_NONE;
    }
    s_usScore = 0;
    s_ucLives = AWTO_AST_LIVES;
    s_ucWave = 0;
    s_ucShState = AWTO_AST_STATE_DEAD;                                              // appears at once (timer 0)
    s_ucShTimer = 0;
    s_ucWaveTimer = 0;
    s_usSaucerTimer = AWTO_AST_SAUCER_MIN;
    AstNewWave();
}

static void AstShoot(BYTE ucType, int16_t sX, int16_t sY, BYTE ucAng, BYTE ucSpeed, int16_t sVx0, int16_t sVy0)
{
    BYTE ucTtl = (ucType == AWTO_AST_T_SHOT) ? AWTO_AST_SHOT_TTL : AWTO_AST_SSHOT_TTL;

    AstDir(ucAng);
    AstAdd(ucType, sX + (((int16_t)s_cDx * AWTO_AST_TIP) >> 7), sY + (((int16_t)s_cDy * AWTO_AST_TIP) >> 7),
           (int8_t)((((int16_t)s_cDx * ucSpeed) >> 7) + sVx0), (int8_t)((((int16_t)s_cDy * ucSpeed) >> 7) + sVy0), ucTtl);
}

static BYTE AstCount(BYTE ucFirst, BYTE ucLast)                                     // live objects with a type in the range
{
    BYTE ucI;
    BYTE ucN = 0;

    for(ucI = 0; ucI < AWTO_AST_N_OBJ; ucI++)
    {
        if((s_atObj[ucI].ucType >= ucFirst) && (s_atObj[ucI].ucType <= ucLast))
        {
            ucN++;
        }
    }
    return ucN;
}

static void AstShipThink(void)                                                      // autopilot: nearest rock / saucer, lead, turn, fire, wander
{
    BYTE ucI;
    BYTE ucBest = AWTO_AST_NONE;
    WORD usBest = 0xFFFF;
    int16_t sDx;
    int16_t sDy;
    WORD usD;
    long lCross;
    long lDot;
    int16_t sA;
    int16_t sB;
    BYTE ucLead;
    BYTE ucThrust = 0;

    for(ucI = 0; ucI < AWTO_AST_N_OBJ; ucI++)
    {
        if((s_atObj[ucI].ucType >= AWTO_AST_T_ROCK_L) && (s_atObj[ucI].ucType <= AWTO_AST_T_SAUCER_S))
        {
            sDx = AstDiff(s_atObj[ucI].sX - s_sShX, AWTO_AST_FPW) >> AWTO_AST_FP;
            sDy = AstDiff(s_atObj[ucI].sY - s_sShY, AWTO_AST_FPH) >> AWTO_AST_FP;
            usD = (WORD)(sDx * sDx) + (WORD)(sDy * sDy);
            if(usD < usBest)
            {
                usBest = usD;
                ucBest = ucI;
            }
        }
    }
    if(ucBest != AWTO_AST_NONE)
    {
        sDx = AstDiff(s_atObj[ucBest].sX - s_sShX, AWTO_AST_FPW);
        sDy = AstDiff(s_atObj[ucBest].sY - s_sShY, AWTO_AST_FPH);
        sA = (sDx < 0) ? -sDx : sDx;
        sB = (sDy < 0) ? -sDy : sDy;
        usD = (WORD)(sA + sB - (((sA < sB) ? sA : sB) >> 1));                       // distance, fp
        ucLead = (BYTE)((WORD)(sA + sB) >> AWTO_AST_LEAD_SHIFT);
        if(ucLead > AWTO_AST_SHOT_TTL)
        {
            ucLead = AWTO_AST_SHOT_TTL;
        }
        sDx += (int16_t)(s_atObj[ucBest].cVx - s_cShVx) * ucLead;
        sDy += (int16_t)(s_atObj[ucBest].cVy - s_cShVy) * ucLead;
        AstDir(s_ucShAng);
        lCross = (long)s_cDx * sDy - (long)s_cDy * sDx;                             // > 0: the target is clockwise of the heading
        lDot = (long)s_cDx * sDx + (long)s_cDy * sDy;
        if(lCross < 0)
        {
            lCross = -lCross;
            s_ucShAng = (BYTE)((s_ucShAng + ((lCross > (long)usD * AWTO_AST_TURN_FAST) ? 2 : 1)) & (AWTO_AST_ANGLES - 1));
        }
        else if(lCross > 0)
        {
            s_ucShAng = (BYTE)((s_ucShAng - ((lCross > (long)usD * AWTO_AST_TURN_FAST) ? 2 : 1)) & (AWTO_AST_ANGLES - 1));
        }
        if((lCross < (long)usD * AWTO_AST_AIM_TOL) && (lDot > 0) && (usD < AWTO_AST_RANGE) && (s_ucShCd == 0) && (AstCount(AWTO_AST_T_SHOT, AWTO_AST_T_SHOT) < AWTO_AST_SHOTS_MAX))
        {
            AstShoot(AWTO_AST_T_SHOT, s_sShX, s_sShY, s_ucShAng, AWTO_AST_SHOT_SPEED, s_cShVx, s_cShVy);
            AstSnd(AWTO_AST_SND_FIRE);
            s_ucShCd = AWTO_AST_FIRE_CD;
        }
        if((usD < AWTO_AST_DANGER) && (lDot < 0))
        {
            ucThrust = 1;                                                           // a rock close behind: fly away
        }
    }
    if((s_ucThrustLeft == 0) && ((g_usAwtoAstStep & AWTO_AST_WANDER_MASK) == 0) && ((AstRnd() & 1) != 0))
    {
        s_ucThrustLeft = AWTO_AST_THRUST_STEPS;
    }
    if(s_ucThrustLeft != 0)
    {
        s_ucThrustLeft--;
        ucThrust = 1;
    }
    s_ucShThrust = ucThrust;
    if(s_ucShCd != 0)
    {
        s_ucShCd--;
    }
}

static int8_t AstClampV(int16_t sV)
{
    if(sV > AWTO_AST_VMAX)
    {
        return AWTO_AST_VMAX;
    }
    if(sV < -AWTO_AST_VMAX)
    {
        return -AWTO_AST_VMAX;
    }
    return (int8_t)sV;
}

static void AstShipMove(void)
{
    if(s_ucShThrust != 0)
    {
        AstDir(s_ucShAng);
        s_cShVx = AstClampV(s_cShVx + (((int16_t)s_cDx * AWTO_AST_ACC) >> 7));
        s_cShVy = AstClampV(s_cShVy + (((int16_t)s_cDy * AWTO_AST_ACC) >> 7));
    }
    if((g_usAwtoAstStep & AWTO_AST_DRAG_MASK) == 0)
    {
        s_cShVx -= (s_cShVx > 0) - (s_cShVx < 0);
        s_cShVy -= (s_cShVy > 0) - (s_cShVy < 0);
    }
    s_sShX += s_cShVx;
    s_sShY += s_cShVy;
    if(s_sShX < 0)
    {
        s_sShX += AWTO_AST_FPW;
    }
    else if(s_sShX >= AWTO_AST_FPW)
    {
        s_sShX -= AWTO_AST_FPW;
    }
    if(s_sShY < 0)
    {
        s_sShY += AWTO_AST_FPH;
    }
    else if(s_sShY >= AWTO_AST_FPH)
    {
        s_sShY -= AWTO_AST_FPH;
    }
}

static void AstSaucerAct(BYTE ucI)                                                  // course change and shots
{
    BYTE ucAng;
    int16_t sDx;
    int16_t sDy;
    BYTE ucK;
    int16_t sBest = -32767;
    int16_t sV;

    if(((g_usAwtoAstStep + ucI) & 15) == 0)
    {
        s_atObj[ucI].cVy = (int8_t)(((int8_t)(AstRnd() % 3) - 1) * AWTO_AST_SAUCER_VY);
    }
    if(s_atObj[ucI].ucAux != 0)
    {
        s_atObj[ucI].ucAux--;
        return;
    }
    s_atObj[ucI].ucAux = AWTO_AST_SAUCER_FIRE;
    ucAng = AstRnd() & (AWTO_AST_ANGLES - 1);
    if((s_atObj[ucI].ucType == AWTO_AST_T_SAUCER_S) && (s_ucShState == AWTO_AST_STATE_ALIVE))     // the small saucer aims (heading with the best dot product)
    {
        sDx = AstDiff(s_sShX - s_atObj[ucI].sX, AWTO_AST_FPW) >> AWTO_AST_LEAD_SHIFT;
        sDy = AstDiff(s_sShY - s_atObj[ucI].sY, AWTO_AST_FPH) >> AWTO_AST_LEAD_SHIFT;
        for(ucK = 0; ucK < AWTO_AST_ANGLES; ucK++)
        {
            AstDir(ucK);
            sV = (int16_t)s_cDx * sDx + (int16_t)s_cDy * sDy;
            if(sV > sBest)
            {
                sBest = sV;
                ucAng = ucK;
            }
        }
        ucAng = (BYTE)((ucAng + (AstRnd() & 3) - 1) & (AWTO_AST_ANGLES - 1));
    }
    AstShoot(AWTO_AST_T_SSHOT, s_atObj[ucI].sX, s_atObj[ucI].sY, ucAng, AWTO_AST_SSHOT_SPEED, 0, 0);
}

static void AstMove(void)
{
    BYTE ucI;
    BYTE ucT;

    for(ucI = 0; ucI < AWTO_AST_N_OBJ; ucI++)
    {
        ucT = s_atObj[ucI].ucType;
        if(ucT == AWTO_AST_T_NONE)
        {
            continue;
        }
        if(ucT == AWTO_AST_T_BOOM)
        {
            s_atObj[ucI].ucAux++;
            if(s_atObj[ucI].ucAux >= ((s_atObj[ucI].cVx > AWTO_AST_BOOM_BIG) ? AWTO_AST_BOOM_SHIP_LIFE : AWTO_AST_BOOM_LIFE))
            {
                s_atObj[ucI].ucType = AWTO_AST_T_NONE;
            }
            continue;
        }
        if((ucT == AWTO_AST_T_SHOT) || (ucT == AWTO_AST_T_SSHOT))
        {
            s_atObj[ucI].ucAux--;
            if(s_atObj[ucI].ucAux == 0)
            {
                s_atObj[ucI].ucType = AWTO_AST_T_NONE;
                continue;
            }
        }
        if((ucT == AWTO_AST_T_SAUCER_L) || (ucT == AWTO_AST_T_SAUCER_S))
        {
            AstSaucerAct(ucI);
        }
        s_atObj[ucI].sX += s_atObj[ucI].cVx;
        s_atObj[ucI].sY += s_atObj[ucI].cVy;
        if(((ucT == AWTO_AST_T_SAUCER_L) || (ucT == AWTO_AST_T_SAUCER_S)) && ((s_atObj[ucI].sX < 0) || (s_atObj[ucI].sX >= AWTO_AST_FPW)))
        {
            s_atObj[ucI].ucType = AWTO_AST_T_NONE;                                  // the saucer leaves the screen
            continue;
        }
        if(s_atObj[ucI].sX < 0)
        {
            s_atObj[ucI].sX += AWTO_AST_FPW;
        }
        else if(s_atObj[ucI].sX >= AWTO_AST_FPW)
        {
            s_atObj[ucI].sX -= AWTO_AST_FPW;
        }
        if(s_atObj[ucI].sY < 0)
        {
            s_atObj[ucI].sY += AWTO_AST_FPH;
        }
        else if(s_atObj[ucI].sY >= AWTO_AST_FPH)
        {
            s_atObj[ucI].sY -= AWTO_AST_FPH;
        }
    }
}

static void AstCollide(void)
{
    BYTE ucI;
    BYTE ucJ;
    BYTE ucT;
    BYTE ucU;

    for(ucI = 0; ucI < AWTO_AST_N_OBJ; ucI++)                                       // ship shots against rocks and saucers
    {
        if(s_atObj[ucI].ucType != AWTO_AST_T_SHOT)
        {
            continue;
        }
        for(ucJ = 0; ucJ < AWTO_AST_N_OBJ; ucJ++)
        {
            AstPoll();
            ucU = s_atObj[ucJ].ucType;
            if((ucU >= AWTO_AST_T_ROCK_L) && (ucU <= AWTO_AST_T_SAUCER_S) &&
               ((AstNear(s_atObj[ucI].sX, s_atObj[ucI].sY, s_atObj[ucJ].sX, s_atObj[ucJ].sY, AstHit(ucU) + AstHit(AWTO_AST_T_SHOT)) != 0) ||
                (AstNear(s_atObj[ucI].sX - (s_atObj[ucI].cVx >> 1), s_atObj[ucI].sY - (s_atObj[ucI].cVy >> 1), s_atObj[ucJ].sX, s_atObj[ucJ].sY, AstHit(ucU) + AstHit(AWTO_AST_T_SHOT)) != 0)))   // and halfway back along the step
            {
                s_atObj[ucI].ucType = AWTO_AST_T_NONE;
                AstBreak(ucJ);
                break;
            }
        }
    }
    if(s_ucShState != AWTO_AST_STATE_ALIVE)
    {
        return;
    }
    for(ucI = 0; ucI < AWTO_AST_N_OBJ; ucI++)                                       // the ship against rocks, saucers and their shots
    {
        ucT = s_atObj[ucI].ucType;
        if(((ucT >= AWTO_AST_T_ROCK_L) && (ucT <= AWTO_AST_T_SAUCER_S)) || (ucT == AWTO_AST_T_SSHOT))
        {
            if(AstNear(s_atObj[ucI].sX, s_atObj[ucI].sY, s_sShX, s_sShY, AstHit(ucT) + AWTO_AST_SHIP_HIT) != 0)
            {
                if(ucT == AWTO_AST_T_SSHOT)
                {
                    s_atObj[ucI].ucType = AWTO_AST_T_NONE;
                }
                else
                {
                    AstBreak(ucI);
                }
                AstShipDie();
                return;
            }
        }
    }
}

static void AstSpawnSaucer(void)
{
    BYTE ucSmall = (BYTE)((AstRnd() % 100) < AWTO_AST_SAUCER_SMALL_PCT);
    BYTE ucRight = AstRnd() & 1;
    int16_t sY = (int16_t)(AWTO_AST_SAUCER_MARGIN + AstRnd() % (AWTO_AST_H - 2 * AWTO_AST_SAUCER_MARGIN)) << AWTO_AST_FP;
    int8_t cV = ucSmall ? AWTO_AST_SAUCER_VX_S : AWTO_AST_SAUCER_VX;

    AstAdd(ucSmall ? AWTO_AST_T_SAUCER_S : AWTO_AST_T_SAUCER_L, ucRight ? (AWTO_AST_FPW - 1) : 0, sY, ucRight ? (int8_t)-cV : cV, 0, AWTO_AST_SAUCER_FIRE);
}

static void AstWorld(void)                                                          // waves, saucers, respawn, game over, sound state
{
    BYTE ucI;
    BYTE ucFree = 1;
    BYTE ucBg = AWTO_AST_BG_NONE;

    if(AstCount(AWTO_AST_T_ROCK_L, AWTO_AST_T_ROCK_S) == 0)
    {
        if(s_ucWaveTimer == 0)
        {
            s_ucWaveTimer = AWTO_AST_WAVE_STEPS;
        }
        else if(--s_ucWaveTimer == 0)
        {
            AstNewWave();
        }
    }
    if((AstCount(AWTO_AST_T_SAUCER_L, AWTO_AST_T_SAUCER_S) == 0) && (AstCount(AWTO_AST_T_ROCK_L, AWTO_AST_T_ROCK_S) != 0))
    {
        if(s_usSaucerTimer != 0)
        {
            s_usSaucerTimer--;
        }
        else
        {
            AstSpawnSaucer();
            s_usSaucerTimer = AWTO_AST_SAUCER_MIN + (AstRnd() % AWTO_AST_SAUCER_RANGE);
        }
    }
    if(s_ucShState == AWTO_AST_STATE_DEAD)
    {
        if(s_ucShTimer != 0)
        {
            s_ucShTimer--;
        }
        else
        {
            for(ucI = 0; ucI < AWTO_AST_N_OBJ; ucI++)
            {
                if(((s_atObj[ucI].ucType >= AWTO_AST_T_ROCK_L) && (s_atObj[ucI].ucType <= AWTO_AST_T_SAUCER_S)) &&
                   (AstNear(s_atObj[ucI].sX, s_atObj[ucI].sY, AWTO_AST_FPW / 2, AWTO_AST_FPH / 2, AWTO_AST_CLEAR_PX) != 0))
                {
                    ucFree = 0;
                }
            }
            if(ucFree != 0)
            {
                s_ucShState = AWTO_AST_STATE_ALIVE;
                s_sShX = AWTO_AST_FPW / 2;
                s_sShY = AWTO_AST_FPH / 2;
                s_cShVx = 0;
                s_cShVy = 0;
                s_ucShAng = AWTO_AST_UP;
                s_ucShCd = 0;
            }
        }
    }
    else if(s_ucShState == AWTO_AST_STATE_OVER)
    {
        if(--s_ucShTimer == 0)
        {
            AstNewGame();
        }
    }
    if(AstCount(AWTO_AST_T_SAUCER_L, AWTO_AST_T_SAUCER_S) != 0)
    {
        ucBg = AWTO_AST_BG_SAUCER;
    }
    if((s_ucShState == AWTO_AST_STATE_ALIVE) && (s_ucShThrust != 0))
    {
        ucBg = AWTO_AST_BG_THRUST;                                                  // the ship's engine wins over the saucer's siren
    }
    AstBg(ucBg);
}

static void AstDigits(void)
{
    WORD usV = s_usScore;
    BYTE ucK;

    for(ucK = AWTO_AST_DIGITS; ucK > 0; ucK--)
    {
        s_aucDig[ucK - 1] = (uint8_t)(usV % AWTO_AST_DEC);
        usV /= AWTO_AST_DEC;
    }
    s_ucDigN = AWTO_AST_DIGITS;                                                     // leading zeros trimmed, two digits at least
    while((s_ucDigN > 2) && (s_aucDig[AWTO_AST_DIGITS - s_ucDigN] == 0))
    {
        s_ucDigN--;
    }
}

static void AstTick(void)
{
    g_usAwtoAstStep++;
    AstMove();
    AstPoll();
    s_ucShThrust = 0;
    if(s_ucShState == AWTO_AST_STATE_ALIVE)
    {
        AstShipThink();
        AstShipMove();
    }
    AstPoll();
    AstCollide();
    AstWorld();
}

static BYTE AstDue(void)                                                            // game ticks due now (0..AWTO_AST_MAX_CATCHUP), the schedule advanced by their periods
{
    BYTE ucN = 0;
    WORD usNow = (WORD)AwtoMs();

#ifdef _AWTO_AST_FIXED_TICKS                                                        // test build: AWTO_AST_TICKS per frame, unpaced (frame content = frame number: saver_frames_md5.py)
    usNow = s_usTickAt - 1;                                                         // never due: the schedule stays as it is
    ucN = AWTO_AST_TICKS;
#endif
    while((ucN < AWTO_AST_MAX_CATCHUP) && ((WORD)(usNow - s_usTickAt) < AWTO_AST_HALF_MS))
    {
        s_usTickAt += AWTO_AST_TICK_MS;
        ucN++;
    }
    if((WORD)(usNow - s_usTickAt) < AWTO_AST_HALF_MS)
    {
        s_usTickAt = usNow + AWTO_AST_TICK_MS;                                      // still behind after the cap: resync
    }
    return ucN;
}

static void AstStep(BYTE ucTicks)                                                   // the frame's game ticks, then the HUD numbers
{
    BYTE ucK;

    for(ucK = 0; ucK < ucTicks; ucK++)
    {
        AstPoll();
        AstTick();
    }
    AstDigits();
    s_ucHudDirty = (BYTE)((s_usHudScore != s_usScore) || (s_ucHudLives != s_ucLives));
    s_usHudScore = s_usScore;
    s_ucHudLives = s_ucLives;
}

#pragma place bank(8)
static __code uint8_t s_tAstBit[AWTO_AST_BIT_MASK + 1] = {0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01};   // bit index in a byte -> mask (MSB first, osd_lines order)
#pragma place bank(8)
static __code uint8_t s_tAstTileOff[AWTO_AST_BAND_ROWS] = {0, OSD_TILE_BYTES, 2 * OSD_TILE_BYTES, 3 * OSD_TILE_BYTES, 4 * OSD_TILE_BYTES, 5 * OSD_TILE_BYTES};   // canvas tile row -> byte offset
#pragma place bank(8)
static __code uint8_t s_tAstRowY[AWTO_AST_BAND_ROWS + 1] = {0, AWTO_AST_TH, 2 * AWTO_AST_TH, 3 * AWTO_AST_TH, 4 * AWTO_AST_TH, 5 * AWTO_AST_TH, 6 * AWTO_AST_TH};   // canvas tile row -> y
typedef char s_tAstLineCheck[((AWTO_AST_TW == 12) && (AWTO_AST_BAND_ROWS == 6)) ? 1 : -1];   // AWTO_AST_MUL_TW and s_tAstTileOff are written for these

#define AWTO_AST_LINE_OFS                       64                                  // byte coordinate offset: endpoints within 64 px of the pass window (lines < 64 px)
#define AWTO_AST_PLOT()                         {                                                                                   \
            ucPx = (BYTE)(ucX - AWTO_AST_LINE_OFS);                                                                                 \
            ucPy = (BYTE)(ucY - AWTO_AST_LINE_OFS);                                                                                 \
            if((ucPx < AWTO_AST_TW) && ((BYTE)(ucPy - ucC0) < ucH))                                                                 \
            {                                                                                                                       \
                ucIn = 1;                                                                                                           \
                ucT = ucPy / (BYTE)AWTO_AST_TH;                                                                                     \
                ucPy = ucPy % (BYTE)AWTO_AST_TH;                                                                                    \
                ucPx = (BYTE)(AWTO_AST_MUL_TW(ucPy) + ucPx);                                                                        \
                g_aucScPix[s_tAstTileOff[ucT] + (ucPx >> AWTO_AST_BYTE_BITS)] |= s_tAstBit[ucPx & AWTO_AST_BIT_MASK];              \
            }                                                                                                                       \
            else if(ucIn != 0)                                                                                                      \
            {                                                                                                                       \
                break;                                                                                                              \
            }                                                                                                                       \
        }                                                                                                                           // one px; a straight line that left the window never returns
#pragma place bank(8)
static void AstLine(void)                                                          // s_sL* (canvas px): osd_line's Bresenham (error = major / 2), every px walked, px inside the pass plotted
{
    __data BYTE ucX = (BYTE)(s_sLx0 + AWTO_AST_LINE_OFS);                                // byte coordinates: lines are < AWTO_AST_LINE_OFS px and touch the pass
    __data BYTE ucY = (BYTE)(s_sLy0 + AWTO_AST_LINE_OFS);
    BYTE ucX1 = (BYTE)(s_sLx1 + AWTO_AST_LINE_OFS);
    BYTE ucY1 = (BYTE)(s_sLy1 + AWTO_AST_LINE_OFS);
    __data BYTE ucC0 = (BYTE)s_sClip0;
    __data BYTE ucH = (BYTE)(s_sBandH - s_sClip0);
    int8_t cSx = (ucX1 >= ucX) ? 1 : -1;
    int8_t cSy = (ucY1 >= ucY) ? 1 : -1;
    BYTE ucDx = (cSx > 0) ? (BYTE)(ucX1 - ucX) : (BYTE)(ucX - ucX1);
    BYTE ucDy = (cSy > 0) ? (BYTE)(ucY1 - ucY) : (BYTE)(ucY - ucY1);
    __data BYTE ucErr;
    BYTE ucN;
    __data BYTE ucIn = 0;
    BYTE ucPx;
    BYTE ucPy;
    BYTE ucT;

    if(ucDx >= ucDy)
    {
        ucN = ucDx;
        ucErr = ucDx >> 1;
        for(;;)
        {
            AWTO_AST_PLOT();
            if(ucN == 0)
            {
                break;
            }
            ucN--;
            ucX += cSx;
            if(ucErr < ucDy)
            {
                ucErr += ucDx - ucDy;
                ucY += cSy;
            }
            else
            {
                ucErr -= ucDy;
            }
        }
    }
    else
    {
        ucN = ucDy;
        ucErr = ucDy >> 1;
        for(;;)
        {
            AWTO_AST_PLOT();
            if(ucN == 0)
            {
                break;
            }
            ucN--;
            ucY += cSy;
            if(ucErr < ucDx)
            {
                ucErr += ucDy - ucDx;
                ucX += cSx;
            }
            else
            {
                ucErr -= ucDx;
            }
        }
    }
}

#pragma place bank(8)
static void AstShape(BYTE ucShape, BYTE ucShift, BYTE ucRot)                        // polylines of a shape around (s_sRx, s_sRy), y up, turned ucRot quarter turns
{
    __data WORD usP = g_tAstOff[ucShape];
    BYTE ucN;
    BYTE ucI;
    __data int16_t sX;
    __data int16_t sY;
    int16_t sT;
    __data int16_t sPx = 0;
    __data int16_t sPy = 0;
    BYTE ucPoly;

    for(ucPoly = 0; ucPoly < AWTO_AST_MAX_POLYS; ucPoly++)                          // walks const data: bound = the most polylines of any shape (generated), the 0 count ends a shape earlier
    {
        ucN = (BYTE)g_tAstData[usP++];
        if(ucN == 0)
        {
            break;
        }
        for(ucI = 0; ucI < ucN; ucI++)
        {
            AstPoll();
            sX = g_tAstData[usP++];
            sY = g_tAstData[usP++];
            if((ucRot & 1) != 0)
            {
                sT = sX;
                sX = -sY;
                sY = sT;
            }
            if((ucRot & 2) != 0)
            {
                sX = -sX;
                sY = -sY;
            }
            sX = s_sRx + (sX >> ucShift);
            sY = s_sRy - (sY >> ucShift);
            if((ucI != 0) && !(((sPx < 0) && (sX < 0)) || ((sPx >= AWTO_AST_TW) && (sX >= AWTO_AST_TW)) ||
                               ((sPy < s_sClip0) && (sY < s_sClip0)) || ((sPy >= s_sBandH) && (sY >= s_sBandH))))   // AstLine walks every pixel of a line: skip lines wholly outside the clip
            {
                s_sLx0 = sPx;
                s_sLy0 = sPy;
                s_sLx1 = sX;
                s_sLy1 = sY;
                AstLine();
            }
            sPx = sX;
            sPy = sY;
        }
    }
}

#pragma place bank(8)                                                               // the draw path shares one bank (no trampoline per call) and keeps bank 13 free
static BYTE AstCull(int16_t sPx, int16_t sPy, BYTE ucR)                             // object centre (playfield px) -> s_sRx / s_sRy; 0 when it misses the pass
{
    __data int16_t sT = sPx - s_sOx + ucR;

    if(sT < 0)
    {
        sT += AWTO_AST_W;
    }
    else if(sT >= AWTO_AST_W)
    {
        sT -= AWTO_AST_W;
    }
    if(sT >= (AWTO_AST_TW + 2 * ucR))
    {
        return 0;
    }
    s_sRx = sT - ucR;
    sT = sPy - s_sOy - s_sClip0 + ucR;                                              // against the clip rows of the band (the changed tiles)
    if(sT < 0)
    {
        sT += AWTO_AST_H;
    }
    else if(sT >= AWTO_AST_H)
    {
        sT -= AWTO_AST_H;
    }
    if(sT >= (s_sBandH - s_sClip0 + 2 * ucR))
    {
        return 0;
    }
    s_sRy = sT - ucR + s_sClip0;
    return 1;
}

#pragma place bank(8)
static void AstDrawBoom(BYTE ucSize, BYTE ucAge)
{
    BYTE ucK;
    BYTE ucLife = (ucSize > AWTO_AST_BOOM_BIG) ? AWTO_AST_BOOM_SHIP_LIFE : AWTO_AST_BOOM_LIFE;
    int16_t sR = ((int16_t)ucSize * (ucAge + 1)) / ucLife;                          // grows to ucSize over the boom's life
    int16_t sR0 = (sR * 2) / 3;

    for(ucK = 0; ucK < AWTO_AST_BOOM_DOTS; ucK++)
    {
        AstPoll();
        AstDir((BYTE)(ucK * AWTO_AST_BOOM_STEP + ucAge));
        s_sLx0 = s_sRx + (((int16_t)s_cDx * sR0) >> 7);
        s_sLy0 = s_sRy + (((int16_t)s_cDy * sR0) >> 7);
        s_sLx1 = s_sRx + (((int16_t)s_cDx * sR) >> 7);
        s_sLy1 = s_sRy + (((int16_t)s_cDy * sR) >> 7);
        AstLine();
    }
}

#pragma place bank(8)
static void AstDrawObj(BYTE ucI)
{
    BYTE ucT = s_atObj[ucI].ucType;

    if(ucT <= AWTO_AST_T_ROCK_S)
    {
        AstShape(AWTO_AST_SH_ROCK0 + (s_atObj[ucI].ucAux & (AWTO_AST_SHAPES_PER_ROCK - 1)), (BYTE)(AWTO_AST_SHIFT_ROCK_L + ucT - AWTO_AST_T_ROCK_L), 0);
    }
    else if(ucT <= AWTO_AST_T_SAUCER_S)
    {
        AstShape(AWTO_AST_SH_SAUCER, (ucT == AWTO_AST_T_SAUCER_L) ? AWTO_AST_SHIFT_SAUCER_L : AWTO_AST_SHIFT_SAUCER_S, 0);
    }
    else if(ucT <= AWTO_AST_T_SSHOT)
    {
        s_sLx0 = s_sRx;                                                             // 2 x 2 px: two 2 px lines
        s_sLy0 = s_sRy;
        s_sLx1 = s_sRx + 1;
        s_sLy1 = s_sRy;
        AstLine();
        s_sLx0 = s_sRx;
        s_sLy0 = s_sRy + 1;
        s_sLx1 = s_sRx + 1;
        s_sLy1 = s_sRy + 1;
        AstLine();
    }
    else
    {
        AstDrawBoom((BYTE)s_atObj[ucI].cVx, s_atObj[ucI].ucAux);
    }
}

#pragma place bank(8)
static void AstDrawShip(BYTE ucAng, BYTE ucFlame)                                   // centre in s_sRx / s_sRy
{
    BYTE ucR = ucAng % AWTO_AST_QUARTER;
    BYTE ucQ = (BYTE)(ucAng / AWTO_AST_QUARTER);

    AstShape(AWTO_AST_SH_HULL + ucR, AWTO_AST_SHIFT_SHIP, ucQ);
    if(ucFlame != 0)
    {
        AstShape(AWTO_AST_SH_FLAME + ucR, AWTO_AST_SHIFT_SHIP, ucQ);
    }
}

#pragma place bank(8)
static void AstHud(void)                                                            // score and spare ships, top left (passes of band 0, columns below AWTO_AST_HUD_W)
{
    BYTE ucK;

    if((s_sOx >= AWTO_AST_HUD_W) || (s_sOy >= AWTO_AST_HUD_H))
    {
        return;
    }
    for(ucK = 0; ucK < s_ucDigN; ucK++)
    {
        s_sRx = AWTO_AST_HUD_X + (AWTO_AST_DIGITS - s_ucDigN + ucK) * AWTO_AST_DIGIT_ADV - s_sOx;
        s_sRy = AWTO_AST_HUD_BASE - s_sOy;
        AstShape(AWTO_AST_SH_DIGIT + s_aucDig[AWTO_AST_DIGITS - s_ucDigN + ucK], 0, 0);
    }
    for(ucK = 1; ucK < s_ucLives; ucK++)
    {
        s_sRx = AWTO_AST_LIFE_X + (ucK - 1) * AWTO_AST_LIFE_ADV - s_sOx;
        s_sRy = AWTO_AST_LIFE_Y - s_sOy;
        AstShape(AWTO_AST_SH_HULL + (AWTO_AST_UP % AWTO_AST_QUARTER), AWTO_AST_SHIFT_SHIP, AWTO_AST_UP / AWTO_AST_QUARTER);
    }
}

#pragma place bank(8)
static void AstMark(int16_t sX, AstY ucY, BYTE ucR)                                // tiles of the box around (x, y) +- r, wrap-aware (= AstCull's passes) -> s_aucDirty
{
#if(AWTO_AST_WIDE)                                                                  // canvas beyond 360 x 198: word coordinates, any band count (variants, docs/asteroids-resolution.md)
    WORD usC0 = (WORD)(sX - ucR + AWTO_AST_W) / AWTO_AST_TW;
    WORD usNc = (WORD)(sX + ucR + AWTO_AST_W) / AWTO_AST_TW - usC0 + 1;
    WORD usR0 = (WORD)(ucY - ucR + AWTO_AST_H) / AWTO_AST_TH;
    WORD usNr = (WORD)(ucY + ucR + AWTO_AST_H) / AWTO_AST_TH - usR0 + 1;
    WORD usC;
    WORD usK;
    WORD usIdx;
    BYTE ucBit;

    usNc = (usNc > AWTO_AST_COLS) ? AWTO_AST_COLS : usNc;
    usNr = (usNr > AWTO_AST_ROWS) ? AWTO_AST_ROWS : usNr;
    while(usC0 >= AWTO_AST_COLS)
    {
        usC0 -= AWTO_AST_COLS;
    }
    while(usR0 >= AWTO_AST_ROWS)
    {
        usR0 -= AWTO_AST_ROWS;
    }
    for(; usNr > 0; usNr--)
    {
        usIdx = (usR0 / AWTO_AST_BAND_ROWS) * AWTO_AST_COLS;
        ucBit = (BYTE)(1 << (usR0 % AWTO_AST_BAND_ROWS));
        for(usC = usC0, usK = usNc; usK > 0; usK--)
        {
            s_aucDirty[usIdx + usC] |= ucBit;
            usC = (usC == AWTO_AST_COLS - 1) ? 0 : (usC + 1);
        }
        usR0 = (usR0 == AWTO_AST_ROWS - 1) ? 0 : (usR0 + 1);
    }
#else
    BYTE ucC0 = (BYTE)((WORD)(sX - ucR + AWTO_AST_W) >> AWTO_AST_DIV_TW_SHIFT) / AWTO_AST_DIV_TW_REST;    // + one playfield: never negative
    BYTE ucNc = (BYTE)((BYTE)((WORD)(sX + ucR + AWTO_AST_W) >> AWTO_AST_DIV_TW_SHIFT) / AWTO_AST_DIV_TW_REST - ucC0 + 1);
    BYTE ucR0 = (BYTE)((WORD)(ucY - ucR + AWTO_AST_H) >> AWTO_AST_DIV_TH_SHIFT) / AWTO_AST_DIV_TH_REST;
    BYTE ucNr = (BYTE)((BYTE)((WORD)(ucY + ucR + AWTO_AST_H) >> AWTO_AST_DIV_TH_SHIFT) / AWTO_AST_DIV_TH_REST - ucR0 + 1);
    BYTE ucC;
    BYTE ucK;
    BYTE ucIdx;
    BYTE ucBit;

    ucNc = (ucNc > AWTO_AST_COLS) ? AWTO_AST_COLS : ucNc;
    ucNr = (ucNr > AWTO_AST_ROWS) ? AWTO_AST_ROWS : ucNr;
    while(ucC0 >= AWTO_AST_COLS)
    {
        ucC0 -= AWTO_AST_COLS;
    }
    while(ucR0 >= AWTO_AST_ROWS)
    {
        ucR0 -= AWTO_AST_ROWS;
    }
    for(; ucNr > 0; ucNr--)
    {
        if(ucR0 < AWTO_AST_BAND_ROWS)
        {
            ucIdx = 0;
            ucBit = (BYTE)(1 << ucR0);
        }
        else
        {
            ucIdx = AWTO_AST_COLS;
            ucBit = (BYTE)(1 << (ucR0 - AWTO_AST_BAND_ROWS));
        }
        for(ucC = ucC0, ucK = ucNc; ucK > 0; ucK--)
        {
            s_aucDirty[ucIdx + ucC] |= ucBit;
            ucC = (ucC == AWTO_AST_COLS - 1) ? 0 : (BYTE)(ucC + 1);
        }
        ucR0 = (ucR0 == AWTO_AST_ROWS - 1) ? 0 : (BYTE)(ucR0 + 1);
    }
#endif
}

#pragma place bank(8)
static int16_t AstAt(int16_t sP, int8_t cV, int16_t sM)                            // drawn position, px: game position (fp) + velocity x time since the tick, wrapped into sM (fp)
{
    sP = (sP + (((int16_t)cV * s_ucFrac) >> AWTO_AST_FRAC_BITS)) >> AWTO_AST_FP;
    sM = sM >> AWTO_AST_FP;
    if(sP < 0)
    {
        sP += sM;
    }
    else if(sP >= sM)
    {
        sP -= sM;
    }
    return sP;
}

#pragma place bank(8)
static BYTE AstFrac(void)                                                           // time since the last tick (the next is at s_usTickAt), 1/8 ticks
{
#ifdef _AWTO_AST_FIXED_TICKS
    return 0;                                                                       // test build: positions as ticked (frames = frame number)
#else
    WORD usLeft = (WORD)(s_usTickAt - (WORD)AwtoMs());

    if(usLeft > AWTO_AST_TICK_MS)
    {
        return AWTO_AST_FRAC_MAX;                                                   // the tick is due now: the next frame runs it
    }
    usLeft = (WORD)(((WORD)(AWTO_AST_TICK_MS - usLeft) << AWTO_AST_FRAC_BITS) / AWTO_AST_TICK_MS);
    return (usLeft > AWTO_AST_FRAC_MAX) ? AWTO_AST_FRAC_MAX : (BYTE)usLeft;
#endif
}

#pragma place bank(8)
static void AstSee(BYTE ucS)                                                        // s_tNow vs slot ucS as last drawn: a change marks both boxes
{
    AstSeen __xdata *pt = &s_atSeen[ucS];

    if((pt->ucR == s_tNow.ucR) && ((pt->ucR == 0) || ((pt->sX == s_tNow.sX) && (pt->ucY == s_tNow.ucY) && (pt->ucKey == s_tNow.ucKey))))
    {
        return;
    }
    if(pt->ucR != 0)
    {
        AstMark(pt->sX, pt->ucY, pt->ucR);
    }
    if(s_tNow.ucR != 0)
    {
        AstMark(s_tNow.sX, s_tNow.ucY, s_tNow.ucR);
    }
    *pt = s_tNow;
}

#pragma place bank(8)
static void AstPrepare(void)                                                        // this frame's drawn positions; tiles of what changed -> s_aucDirty
{
    BYTE ucI;
    BYTE ucT;
    BYTE ucC;
    BYTE ucR;

    for(ucI = 0; ucI < AWTO_AST_N_OBJ; ucI++)
    {
        AstPoll();
        ucT = s_atObj[ucI].ucType;
        s_tNow.ucR = 0;
        if(ucT != AWTO_AST_T_NONE)
        {
            s_tNow.sX = AstAt(s_atObj[ucI].sX, s_atObj[ucI].cVx, AWTO_AST_FPW);
            s_tNow.ucY = (AstY)AstAt(s_atObj[ucI].sY, s_atObj[ucI].cVy, AWTO_AST_FPH);
            s_tNow.ucR = AstRad(ucT);
            s_tNow.ucKey = (BYTE)(ucT * AWTO_AST_KEY_SUBS + ((ucT <= AWTO_AST_T_ROCK_S) ? (s_atObj[ucI].ucAux & (AWTO_AST_SHAPES_PER_ROCK - 1)) :
                                                            ((ucT == AWTO_AST_T_BOOM) ? s_atObj[ucI].ucAux : 0)));
        }
        AstSee(ucI);
    }
    s_tNow.ucR = 0;
    if(s_ucShState == AWTO_AST_STATE_ALIVE)
    {
        s_tNow.sX = AstAt(s_sShX, s_cShVx, AWTO_AST_FPW);
        s_tNow.ucY = (AstY)AstAt(s_sShY, s_cShVy, AWTO_AST_FPH);
        s_tNow.ucR = AWTO_AST_SHIP_R;
        s_tNow.ucKey = (BYTE)(s_ucShAng | (((s_ucShThrust != 0) && (((g_usAwtoAstStep / AWTO_AST_TICKS) & 1) != 0)) ? AWTO_AST_FLAME_KEY : 0));
    }
    AstSee(AWTO_AST_SHIP_SLOT);
    if(s_ucHudDirty != 0)                                                           // score / spare ships changed: their tiles
    {
        for(ucR = 0; ucR < AWTO_AST_HUD_ROWS; ucR++)
        {
            for(ucC = 0; ucC < AWTO_AST_HUD_COLS; ucC++)
            {
                s_aucDirty[ucC] |= (BYTE)(1 << ucR);
            }
        }
    }
}

#if((AWTO_SAVER_INFO == _ON) && (AWTO_AST_BANDS != 2))
#error "info overlay is written for two bands: build variants with -D AWTO_SAVER_INFO=_OFF"
#endif
#if(AWTO_SAVER_INFO == _ON)
#define AWTO_AST_INFO_ACTIVE()                  (SysModeGetModeState() == _MODE_STATUS_ACTIVE)   // as ui_timing (fw/settings/settings_glue.c): the active input's timing
#define AWTO_AST_INFO_VM()                      ((g_stAwtoFreq.ucValid != 0) ? g_stAwtoFreq.ulVFreqmHz : ((DWORD)GET_INPUT_TIMING_VFREQ() * AWTO_AST_INFO_VF_UNIT_MHZ))
#define AWTO_AST_INFO_TXT                       (g_aucScPix + (AWTO_AST_BAND_ROWS - 1) * OSD_TILE_BYTES)   // band 1 has one tile row less: the canvas's last row is free scratch
typedef char s_tAstInfoScratch[((AWTO_AST_ROWS - AWTO_AST_BAND_ROWS < AWTO_AST_BAND_ROWS) && (OSD_TILE_BYTES >= AWTO_AST_INFO_CHARS)) ? 1 : -1];
static __xdata WORD s_usInfoAt;                                                     // scheduled time of the next refresh
#ifdef _AWTO_OSD_HWTEST
static __xdata BYTE s_ucInfoFrames;                                                 // g_usAwtoAstFrames (low byte) at the last refresh; the default image counts g_usAwtoAstFrames from 0 per period (1 B XDATA less)
#endif
static __xdata BYTE s_ucInfoFps;                                                    // 0 = not measured yet
static __xdata BYTE s_ucInfoHz;                                                     // refresh, whole Hz / mHz part (0 = no active input); set once per period
static __xdata WORD s_usInfoFrac;
static __xdata WORD s_usInfoSum;                                                    // checksum of the shown input values: a change redraws

static BYTE AstPutDec(BYTE __xdata *pucL, BYTE ucPos, WORD usV, BYTE ucMin)         // decimal digits (at least ucMin) at ucPos; returns the next position; subtraction per digit: no 16-bit divide
{
    WORD usD;
    BYTE ucK;
    BYTE ucDig;
    BYTE ucOn = 0;

    for(ucK = AWTO_AST_INFO_DEC_DIGITS; ucK > 0; ucK--)
    {
        usD = (ucK == 5) ? AWTO_AST_DEC_TOP : (ucK == 4) ? AWTO_AST_DEC_TOP / AWTO_AST_DEC : (ucK == 3) ? AWTO_AST_DEC * AWTO_AST_DEC : (ucK == 2) ? AWTO_AST_DEC : 1;
        for(ucDig = 0; usV >= usD; ucDig++)
        {
            usV -= usD;
        }
        ucOn |= (BYTE)((ucDig != 0) || (ucK <= ucMin));                             // leading zeros trimmed
        if(ucOn != 0)
        {
            pucL[ucPos++] = ucDig;
        }
    }
    return ucPos;
}

static void AstInfoLine(BYTE __xdata *pucL, BYTE ucLine)                            // glyph ids of one line (AWTO_AST_CH_SPACE = blank)
{
    BYTE ucP;

    memset(pucL, AWTO_AST_CH_SPACE, AWTO_AST_INFO_CHARS);
    if(ucLine == 0)
    {
        if(s_ucInfoHz != 0)
        {
            ucP = AstPutDec(pucL, 0, GET_INPUT_TIMING_HWIDTH(), 1);
            pucL[ucP++] = AWTO_AST_CH_X;
            ucP = AstPutDec(pucL, ucP, GET_INPUT_TIMING_VHEIGHT(), 1);
            ucP = AstPutDec(pucL, ucP + 1, s_ucInfoHz, 1);
            pucL[ucP++] = AWTO_AST_CH_DOT;
            AstPutDec(pucL, ucP, s_usInfoFrac, 3);
        }
    }
    else if(ucLine == 1)                                                            // the game's grid: tiles x cell px, and the scale-up factor of its OSD window
    {
        ucP = AstPutDec(pucL, 0, AWTO_AST_W, 1);
        pucL[ucP++] = AWTO_AST_CH_X;
        ucP = AstPutDec(pucL, ucP, AWTO_AST_H, 1);
        pucL[ucP + 1] = AWTO_AST_CH_X;
        ucP = AstPutDec(pucL, ucP + 2, AWTO_AST_INFO_SCALE_TENTHS / AWTO_AST_INFO_TENTHS, 1);
        pucL[ucP++] = AWTO_AST_CH_DOT;
        AstPutDec(pucL, ucP, AWTO_AST_INFO_SCALE_TENTHS % AWTO_AST_INFO_TENTHS, 1);
    }
    else if(s_ucInfoFps != 0)
    {
        ucP = AstPutDec(pucL, 0, s_ucInfoFps, 1);
        pucL[ucP + 1] = AWTO_AST_CH_F;
        pucL[ucP + 2] = AWTO_AST_CH_P;
        pucL[ucP + 3] = AWTO_AST_CH_S;
    }
}

static void AstInfoTick(WORD usNow)                                                 // once per AWTO_AST_INFO_PERIOD_MS: frames drawn since the last refresh = fps; marks the tiles when a value changed
{
    WORD usSum = 0;
    BYTE ucFps;
    BYTE ucN;

    if((WORD)(usNow - s_usInfoAt) >= AWTO_AST_HALF_MS)
    {
        return;
    }
    s_usInfoAt += AWTO_AST_INFO_PERIOD_MS;
    if((WORD)(usNow - s_usInfoAt) < AWTO_AST_HALF_MS)
    {
        s_usInfoAt = usNow + AWTO_AST_INFO_PERIOD_MS;                               // behind by a period or more: resync
    }
#ifdef _AWTO_OSD_HWTEST
    ucFps = (BYTE)((BYTE)g_usAwtoAstFrames - s_ucInfoFrames);
    s_ucInfoFrames = (BYTE)g_usAwtoAstFrames;
#else
    ucFps = g_usAwtoAstFrames;
    g_usAwtoAstFrames = 0;
#endif
    s_ucInfoHz = 0;
    s_usInfoFrac = 0;
    if(AWTO_AST_INFO_ACTIVE())                                                      // the line's values are set here, once per period (the only 32-bit divides)
    {
        s_ucInfoHz = (BYTE)(AWTO_AST_INFO_VM() / AWTO_AST_THOUSAND);
        s_usInfoFrac = (WORD)(AWTO_AST_INFO_VM() % AWTO_AST_THOUSAND);
        usSum = GET_INPUT_TIMING_HWIDTH() ^ (GET_INPUT_TIMING_VHEIGHT() << AWTO_AST_BYTE_BITS) ^ ((WORD)s_ucInfoHz << AWTO_AST_BYTE_BITS) ^ s_usInfoFrac;
    }
    if((ucFps == s_ucInfoFps) && (usSum == s_usInfoSum))
    {
        return;
    }
    ucN = (usSum == s_usInfoSum) ? AWTO_AST_INFO_FPS_COLS : AWTO_AST_INFO_COLS;     // only the fps changed: its tile row and columns, not the box
    s_ucInfoFps = ucFps;
    while(ucN-- > 0)
    {
        s_aucDirty[AWTO_AST_COLS + AWTO_AST_INFO_COL0 + ucN] |= (BYTE)(((usSum == s_usInfoSum) ? AWTO_AST_INFO_FPS_BITS : AWTO_AST_INFO_BITS) << (AWTO_AST_INFO_ROW0 - AWTO_AST_BAND_ROWS));
    }
    s_usInfoSum = usSum;
}

#pragma place bank(8)
static void AstInfoDraw(void)                                                       // text of the info rows for the pass at (s_sOx, band 1)
{
    BYTE ucL;
    BYTE ucK;
    BYTE ucG;
    BYTE __xdata *aucTxt = AWTO_AST_INFO_TXT;

    for(ucL = 0; ucL < AWTO_AST_INFO_LINES; ucL++)
    {
        AstInfoLine(aucTxt, ucL);
        for(ucK = 0; ucK < AWTO_AST_INFO_CHARS; ucK++)
        {
            ucG = aucTxt[ucK];
            s_sRx = AWTO_AST_INFO_COL0 * AWTO_AST_TW + AWTO_AST_INFO_X + ucK * AWTO_AST_INFO_ADV - s_sOx;
            if((ucG == AWTO_AST_CH_SPACE) || (s_sRx + AWTO_AST_INFO_GW < 0) || (s_sRx >= AWTO_AST_TW))
            {
                continue;
            }
            s_sRy = AWTO_AST_INFO_Y + AWTO_AST_INFO_BASE0 + ucL * AWTO_AST_INFO_LINE_STEP;
            AstShape(AWTO_AST_SH_DIGIT + ucG, AWTO_AST_INFO_SHIFT, 0);
        }
    }
}
#endif

#pragma place bank(8)
static void AstPass(BYTE ucCol, BYTE ucBand)                                        // redraws the band's column if a tile in it changes; uploads only the changed tiles
{
    BYTE ucI;
#if(AWTO_AST_BANDS == 2)
    BYTE ucIdx = (ucBand == 0) ? ucCol : (BYTE)(AWTO_AST_COLS + ucCol);
#else
    WORD ucIdx = (WORD)ucBand * AWTO_AST_COLS + ucCol;
#endif
    BYTE ucDirty = s_aucDirty[ucIdx];
    BYTE ucR0;
    BYTE ucR1;
    BYTE __xdata *pucTile;

    if(ucDirty == 0)
    {
        return;
    }
    s_aucDirty[ucIdx] = 0;
    AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT;
    s_sOx = (int16_t)(((WORD)ucCol << AWTO_AST_BYTE_BITS) + ((WORD)ucCol << AWTO_AST_DIV_TW_SHIFT));   // ucCol * 12, no multiply
#if(AWTO_AST_BANDS == 2)
    s_sOy = (ucBand == 0) ? 0 : AWTO_AST_BAND_H;
    s_ucBandRows = (ucBand == 0) ? AWTO_AST_BAND_ROWS : (BYTE)(AWTO_AST_ROWS - AWTO_AST_BAND_ROWS);   // 2 bands: the second one holds the rest
#else
    s_sOy = (int16_t)ucBand * AWTO_AST_BAND_H;
    s_ucBandRows = (ucBand == AWTO_AST_BANDS - 1) ? (BYTE)(AWTO_AST_ROWS - (AWTO_AST_BANDS - 1) * AWTO_AST_BAND_ROWS) : AWTO_AST_BAND_ROWS;
#endif
    for(ucR0 = 0; (ucDirty & (BYTE)(1 << ucR0)) == 0; ucR0++)                       // clip to the changed rows: objects elsewhere are not drawn
    {
    }
    for(ucR1 = s_ucBandRows - 1; (ucDirty & (BYTE)(1 << ucR1)) == 0; ucR1--)
    {
    }
    s_sClip0 = s_tAstRowY[ucR0];
    s_sBandH = s_tAstRowY[ucR1 + 1];
    memset(g_aucScPix + s_tAstTileOff[ucR0], 0, (WORD)(s_tAstTileOff[ucR1] - s_tAstTileOff[ucR0]) + OSD_TILE_BYTES);
    for(ucI = 0; ucI < AWTO_AST_N_OBJ; ucI++)
    {
        AstPoll();
        if((s_atSeen[ucI].ucR != 0) && (AstCull(s_atSeen[ucI].sX, s_atSeen[ucI].ucY, s_atSeen[ucI].ucR) != 0))
        {
            AstDrawObj(ucI);
        }
    }
    if((s_atSeen[AWTO_AST_SHIP_SLOT].ucR != 0) && (AstCull(s_atSeen[AWTO_AST_SHIP_SLOT].sX, s_atSeen[AWTO_AST_SHIP_SLOT].ucY, AWTO_AST_SHIP_R) != 0))
    {
        AstDrawShip(s_atSeen[AWTO_AST_SHIP_SLOT].ucKey & (AWTO_AST_ANGLES - 1), s_atSeen[AWTO_AST_SHIP_SLOT].ucKey & AWTO_AST_FLAME_KEY);
    }
    if((s_sOx < AWTO_AST_HUD_W) && (s_sOy < AWTO_AST_HUD_H))
    {
        AstHud();
    }
#if(AWTO_SAVER_INFO == _ON)
    if((ucBand != 0) && ((BYTE)(ucCol - AWTO_AST_INFO_COL0) < AWTO_AST_INFO_COLS))
    {
        AstInfoDraw();
    }
#endif
#if(AWTO_AST_BANDS == 2)
    s_usCell0 = ((ucBand == 0) ? 0 : (WORD)(AWTO_AST_BAND_ROWS * AWTO_AST_COLS)) + ucCol;
#else
    s_usCell0 = (WORD)ucBand * (AWTO_AST_BAND_ROWS * AWTO_AST_COLS) + ucCol;
#endif
    pucTile = g_aucScPix;                                                           // running tile pointer: no banked const read next to the cross-bank call
    for(ucI = 0; ucI < s_ucBandRows; ucI++, s_usCell0 += AWTO_AST_COLS, pucTile += OSD_TILE_BYTES)
    {
        if((ucDirty & (BYTE)(1 << ucI)) != 0)
        {
            AstPoll();
            AWTO_AST_TILE(s_usCell0, pucTile);
        }
    }
}

BYTE AwtoAsteroids(BYTE ucCmd)
{
    BYTE ucB;

    if(ucCmd == 0)
    {
        AstBg(AWTO_AST_BG_NONE);
        AwtoPmSound(AWTO_AST_SND_STOP);
        AwtoOsdScreenOff();
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_AST_ARG_OFF, 0);
        return 1;
    }
    if(ucCmd == 2)
    {
        WORD usStart = (WORD)AwtoMs();

        do                                                                          // columns until the time budget is used (clean ones cost a byte test)
        {
            if(g_ucAwtoAstCol == 0)                                                 // frame start: due ticks (0..), interpolated positions, changed tiles
            {
#ifndef _AWTO_AST_FIXED_TICKS
                if(s_ucShown != 0)                                                  // fixed-rate frames (the first one starts at once)
                {
                    if((WORD)(usStart - s_usFrameAt) >= AWTO_AST_HALF_MS)
                    {
                        return 1;                                                   // not due yet
                    }
                    s_usFrameAt += AWTO_AST_FRAME_MS;
                    if((WORD)(usStart - s_usFrameAt) < AWTO_AST_HALF_MS)
                    {
                        s_usFrameAt = usStart + AWTO_AST_FRAME_MS;                  // a frame or more behind: resync, no burst
                    }
                }
#endif
#if(AWTO_SAVER_INFO == _ON)
                if(s_ucShown != 0)
                {
                    AstInfoTick(usStart);
                }
#endif
                AstStep((s_ucShown == 0) ? AWTO_AST_TICKS : AstDue());
                s_ucFrac = AstFrac();
                AstPrepare();
            }
            for(ucB = 0; ucB < AWTO_AST_BANDS; ucB++)
            {
                AstPass(g_ucAwtoAstCol, ucB);
            }
            g_ucAwtoAstCol++;
        } while((g_ucAwtoAstCol < AWTO_AST_COLS) && ((WORD)((WORD)AwtoMs() - usStart) < AWTO_AST_PASS_MS));
        if(g_ucAwtoAstCol < AWTO_AST_COLS)
        {
            return 0;
        }
        g_ucAwtoAstCol = 0;
#if(defined(_AWTO_OSD_HWTEST) || (AWTO_SAVER_INFO == _ON))
        g_usAwtoAstFrames++;                                                        // frames drawn: clock sweep (docs/clock-sweep.md) and the info overlay
#endif
        if(s_ucShown == 0)                                                          // the first frame was drawn hidden
        {
            s_ucShown = 1;
            s_usFrameAt = (WORD)AwtoMs() + AWTO_AST_FRAME_MS;
            osd_tc_show(1);
            AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_AST_ARG_ON, AWTO_AST_FROM_ROM);
        }
        else
        {
            AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_AST_ARG_FRAME, (BYTE)(g_usAwtoAstStep / AWTO_AST_TICKS));
        }
        return 1;
    }
    AwtoOsdScreenBegin();
    ScalerOsdSetColorPalette(AWTO_OSD_ZERO, AWTO_OSD_ZERO, AWTO_OSD_ZERO, AWTO_OSD_ZERO);
    ScalerOsdSetColorPalette(AWTO_AST_BG, AWTO_AST_BG_R, AWTO_AST_BG_G, AWTO_AST_BG_B);
    ScalerOsdSetColorPalette(AWTO_AST_FG, AWTO_RGB_PHOSPHOR_GREEN);                 // same green as the diagnostic console text
    ScalerOsd2FontFunction(_DISABLE);
    AwtoOsdRowCmds(AWTO_AST_ROWS, AWTO_AST_TH, AWTO_AST_COLS);
    AwtoOsdMap1(AWTO_AST_COLS, AWTO_AST_ROWS, (AWTO_AST_FG << AWTO_AST_FG_SHIFT) | AWTO_AST_BG);   // one char command per cell, glyph id = cell index
    AwtoOsdPlaceScaleUp(AWTO_AST_POS_H, AWTO_AST_POS_V, AWTO_AST_COLS, AWTO_AST_ROWS, AWTO_AST_SU_FACTOR);
    osd_canvas_init(&g_scCv, 1, AWTO_AST_BAND_ROWS, g_aucScPix, AWTO_AST_BAND_ROWS * OSD_TILE_BYTES, g_aucScDirty, OSD_DIRTY_BYTES(1, AWTO_AST_BAND_ROWS));
#if(AWTO_AST_BANDS == 2)
    for(ucB = 0; ucB < AWTO_AST_PASSES; ucB++)
    {
        s_aucDirty[ucB] = (BYTE)((1 << ((ucB < AWTO_AST_COLS) ? AWTO_AST_BAND_ROWS : (AWTO_AST_ROWS - AWTO_AST_BAND_ROWS))) - 1);   // every glyph is uploaded once (blank where nothing is)
    }
#else
    {
        WORD usP;

        for(usP = 0; usP < AWTO_AST_PASSES; usP++)
        {
            ucB = (BYTE)(usP / AWTO_AST_COLS);
            s_aucDirty[usP] = (BYTE)((1 << ((ucB == AWTO_AST_BANDS - 1) ? (AWTO_AST_ROWS - (AWTO_AST_BANDS - 1) * AWTO_AST_BAND_ROWS) : AWTO_AST_BAND_ROWS)) - 1);
        }
    }
#endif
    memset(s_atSeen, 0, sizeof(s_atSeen));                                          // nothing drawn yet
    if(s_usRng == 0)
    {
        s_usRng = AWTO_AST_SEED;
    }
#if(AWTO_SAVER_INFO == _ON)
#ifdef _AWTO_OSD_HWTEST
    s_ucInfoFrames = (BYTE)g_usAwtoAstFrames;
#else
    g_usAwtoAstFrames = 0;
#endif
    s_ucInfoFps = 0;
    s_usInfoSum = 0;
    s_usInfoAt = (WORD)AwtoMs() + AWTO_AST_INFO_PERIOD_MS;
#endif
    g_usAwtoAstStep = 0;
    g_ucAwtoAstCol = 0;
    s_usHudScore = 0;
    s_ucHudLives = 0;                                                               // AstNewGame sets the lives: the first step redraws the HUD
    s_ucShown = 0;
    s_usTickAt = (WORD)AwtoMs() + AWTO_AST_TICK_MS;
    s_ucFrac = 0;
    s_ucThrustLeft = 0;
    AstNewGame();
    return 0;
}
#endif                                                         // _AWTO_SAVER_ASTEROIDS
