#include <stdint.h>
#include <string.h>
#include "UserCommonInclude.h"
#include "../../tools/osd_lines/osd_lines.h"

// Asteroids screensaver (docs/asteroids.md): the game runs on the chip (rocks split, shots, saucer, autopilot ship, wrap-around),
// drawn like the scope savers: 32 x 12 tiles of 12 x 18 (384 x 216), 1-bit glyphs, one-tile-column band canvas of scope_saver.c,
// objects culled per pass, tiles uploaded only while they hold (or just held) ink. One game step per frame (column 0).
//   AwtoAsteroids(1) draw   (2) next column, returns 1 when a frame is complete   (0) off
// Shapes: asteroids_data.inc (scripts/gen_asteroids.py: local ROM geometry or own outlines; gitignored).
extern __xdata uint8_t g_aucScPix[];
extern __xdata uint8_t g_aucScDirty[];
extern __xdata osd_canvas g_scCv;
#include "asteroids_data.inc"

#define AWTO_AST_COLS                           32
#define AWTO_AST_ROWS                           12
#define AWTO_AST_TW                             OSD_TILE_W
#define AWTO_AST_TH                             OSD_TILE_H
#define AWTO_AST_W                              (AWTO_AST_COLS * AWTO_AST_TW)       // 384
#define AWTO_AST_H                              (AWTO_AST_ROWS * AWTO_AST_TH)       // 216
#define AWTO_AST_BANDS                          2
#define AWTO_AST_BAND_ROWS                      (AWTO_AST_ROWS / AWTO_AST_BANDS)
#define AWTO_AST_BAND_H                         (AWTO_AST_BAND_ROWS * AWTO_AST_TH)
#define AWTO_AST_BG                             1                                   // palette indexes
#define AWTO_AST_FG                             2
#define AWTO_AST_FG_SHIFT                       4
#define AWTO_AST_BG_R                           2
#define AWTO_AST_BG_G                           2
#define AWTO_AST_BG_B                           6
#define AWTO_AST_FG_R                           235
#define AWTO_AST_FG_G                           235
#define AWTO_AST_FG_B                           225
#define AWTO_AST_SU_FACTOR                      7                                   // as scope_saver.c: 384 x 216 -> 3511 x 1975
#define AWTO_AST_POS_H                          41
#define AWTO_AST_POS_V                          92
#define AWTO_AST_ARG_ON                         0x90                                // sync E9 (no rows: the table is full): value = shape source (AWTO_AST_FROM_ROM)
#define AWTO_AST_ARG_FRAME                      0x91
#define AWTO_AST_ARG_OFF                        0x92

// game units: 1/8 px
#define AWTO_AST_FP                             3
#define AWTO_AST_FPW                            (AWTO_AST_W << AWTO_AST_FP)
#define AWTO_AST_FPH                            (AWTO_AST_H << AWTO_AST_FP)
#define AWTO_AST_N_OBJ                          24
#define AWTO_AST_TICKS                          2                                   // game ticks per drawn frame
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
#define AWTO_AST_SHIFT_ROCK_L                   1                                   // shape units >> shift = px: rock 64 -> 32 / 16 / 8 px
#define AWTO_AST_SHIFT_SAUCER_L                 2
#define AWTO_AST_SHIFT_SAUCER_S                 3
#define AWTO_AST_SHIFT_SHIP                     3                                   // hull tip radius 56 -> 7 px
#define AWTO_AST_ANGLES                         64                                  // ship heading steps, 0 = right, counter-clockwise
#define AWTO_AST_QUARTER                        16
#define AWTO_AST_UP                             16
#define AWTO_AST_RAD_ROCK_L                     17                                  // large rock draw radius, px (64 units >> 1 = 32 px wide); smaller sizes halve
#define AWTO_AST_RAD_SAUCER_L                   11
#define AWTO_AST_SHIP_R                         9                                   // draw radius, px
#define AWTO_AST_SHIP_HIT                       5
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
#define AWTO_AST_BOOM_BIG                       17                                  // boom size above this = the ship's (longer life)
#define AWTO_AST_BOOM_SHIP_SIZE                 20
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
#define AWTO_AST_PASSES                         (AWTO_AST_COLS * AWTO_AST_BANDS)
#define AWTO_AST_TILE_MASK                      ((1 << AWTO_AST_BAND_ROWS) - 1)
#define AWTO_AST_OBJ_BIT                        0x40                                // occupancy bit: the last upload held objects, not only the score / ships
#define AWTO_AST_STATE_ALIVE                    0
#define AWTO_AST_STATE_DEAD                     1                                   // waiting to respawn
#define AWTO_AST_STATE_OVER                     2
#define AWTO_AST_NONE                           0xFF

// sound: cmds of AwtoPmSound (pacman_sound.c)
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

__xdata WORD g_usAwtoAstStep;                                                       // game steps (also read by scripts/asteroids_speed.py)
__xdata BYTE g_ucAwtoAstCol;                                                        // next column of the frame being drawn
static __xdata AstObj s_atObj[AWTO_AST_N_OBJ];
static __xdata uint8_t s_aucOcc[AWTO_AST_PASSES];                                   // per pass: bit n = tile n held ink at its last upload
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
static __xdata BYTE s_ucAny;                                                        // the pass being drawn has ink

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

#ifdef _AWTO_AUDIO_TEST
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
#else
static void AstSnd(BYTE ucCmd)
{
    ucCmd = ucCmd;
}

static void AstBg(BYTE ucState)
{
    ucState = ucState;
}
#endif

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
#ifdef _AWTO_AUDIO_TEST
    BYTE ucBg = AWTO_AST_BG_NONE;
#endif

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
#ifdef _AWTO_AUDIO_TEST
    if(AstCount(AWTO_AST_T_SAUCER_L, AWTO_AST_T_SAUCER_S) != 0)
    {
        ucBg = AWTO_AST_BG_SAUCER;
    }
    if((s_ucShState == AWTO_AST_STATE_ALIVE) && (s_ucShThrust != 0))
    {
        ucBg = AWTO_AST_BG_THRUST;                                                  // the ship's engine wins over the saucer's siren
    }
    AstBg(ucBg);
#endif
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
    s_ucShThrust = 0;
    if(s_ucShState == AWTO_AST_STATE_ALIVE)
    {
        AstShipThink();
        AstShipMove();
    }
    AstCollide();
    AstWorld();
}

static void AstStep(void)                                                           // one frame = AWTO_AST_TICKS game ticks (frames are slow: finer motion and hit tests)
{
    BYTE ucK;

    for(ucK = 0; ucK < AWTO_AST_TICKS; ucK++)
    {
        AstTick();
    }
    AstDigits();
    s_ucHudDirty = (BYTE)((s_usHudScore != s_usScore) || (s_ucHudLives != s_ucLives));
    s_usHudScore = s_usScore;
    s_ucHudLives = s_ucLives;
}

#pragma place bank(8)
static void AstShape(BYTE ucShape, BYTE ucShift, BYTE ucRot)                        // polylines of a shape around (s_sRx, s_sRy), y up, turned ucRot quarter turns
{
    WORD usP = g_tAstOff[ucShape];
    BYTE ucN;
    BYTE ucI;
    int16_t sX;
    int16_t sY;
    int16_t sT;
    int16_t sPx = 0;
    int16_t sPy = 0;

    for(;;)
    {
        ucN = (BYTE)g_tAstData[usP++];
        if(ucN == 0)
        {
            break;
        }
        for(ucI = 0; ucI < ucN; ucI++)
        {
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
                               ((sPy < 0) && (sY < 0)) || ((sPy >= AWTO_AST_BAND_H) && (sY >= AWTO_AST_BAND_H))))   // osd_line walks every pixel of a line, clipped or not: skip lines wholly outside the pass
            {
                osd_line(&g_scCv, sPx, sPy, sX, sY, 1);
            }
            sPx = sX;
            sPy = sY;
        }
    }
}

static BYTE AstCull(int16_t sPx, int16_t sPy, BYTE ucR)                             // object centre (playfield px) -> s_sRx / s_sRy; 0 when it misses the pass
{
    int16_t sT = sPx - s_sOx + ucR;

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
    sT = sPy - s_sOy + ucR;
    if(sT < 0)
    {
        sT += AWTO_AST_H;
    }
    else if(sT >= AWTO_AST_H)
    {
        sT -= AWTO_AST_H;
    }
    if(sT >= (AWTO_AST_BAND_H + 2 * ucR))
    {
        return 0;
    }
    s_sRy = sT - ucR;
    return 1;
}

static void AstDrawBoom(BYTE ucSize, BYTE ucAge)
{
    BYTE ucK;
    BYTE ucLife = (ucSize > AWTO_AST_BOOM_BIG) ? AWTO_AST_BOOM_SHIP_LIFE : AWTO_AST_BOOM_LIFE;
    int16_t sR = ((int16_t)ucSize * (ucAge + 1)) / ucLife;                          // grows to ucSize over the boom's life
    int16_t sR0 = (sR * 2) / 3;

    for(ucK = 0; ucK < AWTO_AST_BOOM_DOTS; ucK++)
    {
        AstDir((BYTE)(ucK * AWTO_AST_BOOM_STEP + ucAge));
        osd_line(&g_scCv, s_sRx + (((int16_t)s_cDx * sR0) >> 7), s_sRy + (((int16_t)s_cDy * sR0) >> 7),
                 s_sRx + (((int16_t)s_cDx * sR) >> 7), s_sRy + (((int16_t)s_cDy * sR) >> 7), 1);
    }
}

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
        osd_pixel(&g_scCv, s_sRx, s_sRy, 1);
        osd_pixel(&g_scCv, s_sRx + 1, s_sRy, 1);
        osd_pixel(&g_scCv, s_sRx, s_sRy + 1, 1);
        osd_pixel(&g_scCv, s_sRx + 1, s_sRy + 1, 1);
    }
    else
    {
        AstDrawBoom((BYTE)s_atObj[ucI].cVx, s_atObj[ucI].ucAux);
    }
}

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

static void AstBlank(void)                                                          // blank canvas (the library's dirty flags are unused here)
{
    memset(g_aucScPix, 0, AWTO_AST_BAND_ROWS * OSD_TILE_BYTES);
}

static void AstInk(void)                                                            // first ink of a pass: start from a blank canvas
{
    if(s_ucAny == 0)
    {
        AstBlank();
        s_ucAny = 1;
    }
}

static BYTE AstTileInk(BYTE ucTile)                                                 // any pixel set in a tile of the canvas
{
    BYTE ucK;
    BYTE ucOr = 0;
    const __xdata uint8_t *pucB = g_aucScPix + (WORD)ucTile * OSD_TILE_BYTES;

    for(ucK = 0; ucK < OSD_TILE_BYTES; ucK++)
    {
        ucOr |= pucB[ucK];
    }
    return ucOr;
}

static BYTE AstPass(BYTE ucCol, BYTE ucBand)                                        // returns 1 when the pass drew or uploaded anything
{
    BYTE ucI;
    BYTE ucBit;
    BYTE ucOcc;
    BYTE ucIdx = (BYTE)(ucBand * AWTO_AST_COLS + ucCol);

    AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT;
    s_sOx = (int16_t)ucCol * AWTO_AST_TW;
    s_sOy = (int16_t)ucBand * AWTO_AST_BAND_H;
    s_ucAny = 0;
    for(ucI = 0; ucI < AWTO_AST_N_OBJ; ucI++)
    {
        if((s_atObj[ucI].ucType != AWTO_AST_T_NONE) && (AstCull(s_atObj[ucI].sX >> AWTO_AST_FP, s_atObj[ucI].sY >> AWTO_AST_FP, AstRad(s_atObj[ucI].ucType)) != 0))
        {
            AstInk();
            AstDrawObj(ucI);
        }
    }
    if((s_ucShState == AWTO_AST_STATE_ALIVE) && (AstCull(s_sShX >> AWTO_AST_FP, s_sShY >> AWTO_AST_FP, AWTO_AST_SHIP_R) != 0))
    {
        AstInk();
        AstDrawShip(s_ucShAng, (BYTE)((s_ucShThrust != 0) && (((g_usAwtoAstStep / AWTO_AST_TICKS) & 1) != 0)));
    }
    ucOcc = s_aucOcc[ucIdx];
    if((s_sOx < AWTO_AST_HUD_W) && (s_sOy < AWTO_AST_HUD_H))
    {
        if((s_ucAny == 0) && (s_ucHudDirty == 0) && ((ucOcc & AWTO_AST_OBJ_BIT) == 0))
        {
            return 0;                                                               // only the unchanged score / ships are here: its glyphs are current
        }
        ucOcc = (s_ucAny != 0) ? (BYTE)(ucOcc | AWTO_AST_OBJ_BIT) : (BYTE)(ucOcc & ~AWTO_AST_OBJ_BIT);
        AstInk();
        AstHud();
    }
    if(s_ucAny == 0)
    {
        if((ucOcc & AWTO_AST_TILE_MASK) == 0)
        {
            return 0;                                                               // empty now and at its last upload
        }
        AstBlank();                                                                 // tiles that held ink are uploaded blank
    }
    s_usCell0 = (WORD)ucBand * AWTO_AST_BAND_ROWS * AWTO_AST_COLS + ucCol;
    for(ucI = 0; ucI < AWTO_AST_BAND_ROWS; ucI++, s_usCell0 += AWTO_AST_COLS)
    {
        ucBit = (BYTE)(1 << ucI);
        if(AstTileInk(ucI) != 0)
        {
            ucOcc |= ucBit;
        }
        else if((ucOcc & ucBit) != 0)
        {
            ucOcc &= (BYTE)~ucBit;
        }
        else
        {
            continue;                                                               // blank before and now: its glyph is already blank
        }
        AwtoOsdTile(s_usCell0, g_aucScPix + (WORD)ucI * OSD_TILE_BYTES);
    }
    s_aucOcc[ucIdx] = ucOcc;
    return 1;
}

BYTE AwtoAsteroids(BYTE ucCmd)
{
    BYTE ucB;

    if(ucCmd == 0)
    {
        AstBg(AWTO_AST_BG_NONE);
#ifdef _AWTO_AUDIO_TEST
        AwtoPmSound(AWTO_AST_SND_STOP);
#endif
        AwtoOsdScreenOff();
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_AST_ARG_OFF, 0);
        return 1;
    }
    if(ucCmd == 2)
    {
        BYTE ucWork;

        do                                                                          // empty columns cost ~1 ms: run on until one has drawn something
        {
            if(g_ucAwtoAstCol == 0)
            {
                AstStep();
            }
            ucWork = 0;
            for(ucB = 0; ucB < AWTO_AST_BANDS; ucB++)
            {
                ucWork |= AstPass(g_ucAwtoAstCol, ucB);
            }
            g_ucAwtoAstCol++;
        } while((g_ucAwtoAstCol < AWTO_AST_COLS) && (ucWork == 0));
        if(g_ucAwtoAstCol < AWTO_AST_COLS)
        {
            return 0;
        }
        g_ucAwtoAstCol = 0;
        if(s_ucShown == 0)                                                          // the first frame was drawn hidden
        {
            s_ucShown = 1;
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
    ScalerOsdSetColorPalette(AWTO_AST_FG, AWTO_AST_FG_R, AWTO_AST_FG_G, AWTO_AST_FG_B);
    ScalerOsd2FontFunction(_DISABLE);
    AwtoOsdRowCmds(AWTO_AST_ROWS, AWTO_AST_TH, AWTO_AST_COLS);
    AwtoOsdMap1(AWTO_AST_COLS, AWTO_AST_ROWS, (AWTO_AST_FG << AWTO_AST_FG_SHIFT) | AWTO_AST_BG);   // one char command per cell, glyph id = cell index
    AwtoOsdPlaceScaleUp(AWTO_AST_POS_H, AWTO_AST_POS_V, AWTO_AST_COLS, AWTO_AST_ROWS, AWTO_AST_SU_FACTOR);
    osd_canvas_init(&g_scCv, 1, AWTO_AST_BAND_ROWS, g_aucScPix, AWTO_AST_BAND_ROWS * OSD_TILE_BYTES, g_aucScDirty, OSD_DIRTY_BYTES(1, AWTO_AST_BAND_ROWS));
    for(ucB = 0; ucB < AWTO_AST_PASSES; ucB++)
    {
        s_aucOcc[ucB] = AWTO_AST_TILE_MASK;                                         // every glyph is uploaded once (blank where nothing is)
    }
    if(s_usRng == 0)
    {
        s_usRng = AWTO_AST_SEED;
    }
    g_usAwtoAstStep = 0;
    g_ucAwtoAstCol = 0;
    s_usHudScore = 0;
    s_ucHudLives = 0;                                                               // AstNewGame sets the lives: the first step redraws the HUD
    s_ucShown = 0;
    s_ucThrustLeft = 0;
    AstNewGame();
#ifndef _AWTO_AUDIO_TEST
    AwtoPmSound(AWTO_AST_SND_FIRE);                                                 // logs "sound unavailable" once (sync E9 86); the game then plays silent
#endif
    return 0;
}
