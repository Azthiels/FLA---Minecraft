/* Shim sobre cubiomes (MIT, Cubitect) para usarlo desde Python con ctypes.
 *
 * Separacion de responsabilidades en sh_scan_tile():
 *   1) generacion matematica de posiciones potenciales -> getStructurePos()  (barato, ~decenas de ns)
 *   2) validacion de viabilidad (bioma/reglas del juego) -> isViableStructurePos() (caro: ruido de bioma)
 *   3) filtros del usuario (caja X/Z, biomas) y registro
 * Los pasos van de lo mas barato a lo mas caro para no hacer consultas de bioma innecesarias.
 */
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "finders.h"
#include "generator.h"
#include "util.h"
/* Tablas del arbol de clima 1.18+ (static const: esta copia es solo para el prefiltro) */
#include "tables/btree18.h"
#include "tables/btree192.h"
#include "tables/btree19.h"
#include "tables/btree20.h"
#include "tables/btree21wd.h"
#include "tables/btree215.h"
#include "tables/btree262.h"
#include "tables/btree263.h"

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

#define NSTAT 11
#define MASKN 512            /* ids de bioma 0..511 (cubiomes llega a ~188) */

enum { ST_REGIONS, ST_POSITIONS, ST_IN_BOX, ST_VIABLE_CALLS, ST_VIABLE_OK, ST_MASK_REJ, ST_TERRAIN_CALLS, ST_FOUND,
       ST_GROUP_SKIP,        /* modo grupos: posiciones descartadas sin consultar bioma (ninguna vecina posible) */
       ST_HALO_CALLS,        /* modo grupos: validaciones de vecinas fuera del tile (incluidas en VIABLE_CALLS) */
       ST_CLIMATE_REJ };     /* prefiltro de clima: descartadas sin calcular el bioma completo */
enum { F_NO_VIABLE = 1,      /* solo benchmark: contar posiciones, sin validar bioma */
       F_NO_TERRAIN = 2,     /* omitir la heuristica de terreno de cubiomes (piramides/templos/mansiones 1.18+) */
       F_GROUPS = 4 };       /* solo estructuras con al menos una vecina valida que entre en el radio (sh_set_groups) */

/* Estados de la ventana del modo grupos */
enum { W_OUT = -3, W_NOPOS = -2, W_UNK = -1, W_BAD = 0, W_OK = 1 };   /* W_OUT = fuera de las cajas */
#define W_USABLE(s) ((s) == W_UNK || (s) == W_OK)

typedef struct {
    Generator g;
    SurfaceNoise sn;
    StructureConfig sc;
    int stype, mc, dim;
    uint64_t seed;
    uint64_t st[NSTAT];
    /* modo grupos */
    int64_t grp_d2;          /* (2*radio)^2 */
    int grp_foot;            /* lado (bloques) de la caja cuadrada conservadora de la estructura */
    int grp_reach;           /* cuantas regiones vecinas hay que mirar en cada eje */
    int *boxes, nboxes;      /* union de cajas del usuario (x0,z0,x1,z1 inclusivo): las vecinas tambien deben estar */
    int wcap;                /* ventana tile+halo reutilizada entre tiles */
    int *wx, *wz, *wb;
    signed char *ws;
    /* prefiltro de clima 1.18+ (sh_set_climate) */
    int pf_on, pf_n;         /* activo / cantidad de hojas (rectangulos de clima) de los biomas buscados */
    int32_t *pf_rect;        /* pf_n x 5 parametros x [min,max]  (orden de pf_ord) */
    int64_t *pf_acc;         /* distancia parcial acumulada por hoja */
    int32_t pf_lo[5], pf_hi[5];   /* dominio cubierto por las hojas de superficie (orden de pf_ord) */
    int pf_ord[5];           /* parametros de clima ordenados de mas a menos selectivo (indices NP_*) */
    int32_t *pf_union;       /* por parametro: union (ordenada, disjunta) de los intervalos de las hojas buscadas */
    int pf_uoff[6];          /* pf_union[2*pf_uoff[k] .. 2*pf_uoff[k+1]) = intervalos del parametro k */
} Handle;

EXPORT int sh_str2mc(const char *s) { return str2mc(s); }
EXPORT const char *sh_struct_name(int stype) { return struct2str(stype); }
EXPORT const char *sh_biome_name(int mc, int id) { return biome2str(mc, id); }

/* 0 = no soportada en esa version. Si lo esta, devuelve dimension+2 (1,2,3). */
EXPORT int sh_supported(int stype, int mc) {
    StructureConfig sc;
    if (!getStructureConfig(stype, mc, &sc)) return 0;
    return sc.dim + 2;
}
EXPORT int sh_region_blocks(int stype, int mc) {
    StructureConfig sc;
    if (!getStructureConfig(stype, mc, &sc)) return 0;
    return sc.regionSize * 16;
}
/* salt, regionSize, chunkRange, dim -> parametros de generacion (para metadatos / analisis posterior) */
EXPORT int sh_struct_config(int stype, int mc, int *out4) {
    StructureConfig sc;
    if (!getStructureConfig(stype, mc, &sc)) return 0;
    out4[0] = sc.salt; out4[1] = sc.regionSize; out4[2] = sc.chunkRange; out4[3] = sc.dim;
    return 1;
}
/* Biomas donde la estructura PUEDE aparecer segun las reglas de cubiomes. */
EXPORT int sh_biome_ok(int mc, int stype, int biome) { return isViableFeatureBiome(mc, stype, biome); }
/* Posicion potencial de una region (para tests). */
EXPORT int sh_struct_pos(int stype, int mc, uint64_t seed, int rx, int rz, int *x, int *z) {
    Pos p;
    if (!getStructurePos(stype, mc, seed, rx, rz, &p)) return 0;
    *x = p.x; *z = p.z;
    return 1;
}

EXPORT void *sh_new(int mc, uint64_t seed, int stype) {
    Handle *h = (Handle *)calloc(1, sizeof(Handle));
    if (!h) return 0;
    if (!getStructureConfig(stype, mc, &h->sc)) { free(h); return 0; }
    h->stype = stype; h->mc = mc; h->seed = seed; h->dim = h->sc.dim;
    setupGenerator(&h->g, mc, 0);
    applySeed(&h->g, h->dim, seed);
    if (stype == End_City) initSurfaceNoise(&h->sn, DIM_END, seed);
    return h;
}
EXPORT void sh_free(void *p) {
    Handle *h = (Handle *)p;
    if (!h) return;
    free(h->boxes); free(h->wx); free(h->wz); free(h->wb); free(h->ws);
    free(h->pf_rect); free(h->pf_acc); free(h->pf_union);
    free(h);
}
EXPORT int sh_nstat(void) { return NSTAT; }

/* Configura el modo grupos. Dos estructuras pueden activarse a la vez si existe un punto P a <= radio de
 * todas sus cajas. Con cajas cuadradas iguales de lado 'foot' eso equivale EXACTAMENTE a
 * (|dx|+foot)^2 + (|dz|+foot)^2 <= (2*radio)^2 (el circulo minimo lo fijan las dos esquinas opuestas).
 * 'boxes' = union de cajas del usuario: una vecina solo cuenta si tambien esta dentro.
 * Devuelve el alcance en regiones (0 = ningun par posible). */
EXPORT int sh_set_groups(void *p, int radius, int foot, const int *boxes, int nboxes) {
    Handle *h = (Handle *)p;
    int rb = h->sc.regionSize * 16;
    int span = 2 * radius - foot;            /* distancia maxima entre posiciones en cada eje */
    h->grp_d2 = (int64_t)(2 * radius) * (2 * radius);
    h->grp_foot = foot;
    h->grp_reach = span < 0 ? 0 : span / rb + 1;
    free(h->boxes);
    h->boxes = 0; h->nboxes = 0;
    if (nboxes > 0) {
        h->boxes = (int *)malloc(sizeof(int) * 4 * nboxes);
        if (!h->boxes) return -1;
        memcpy(h->boxes, boxes, sizeof(int) * 4 * nboxes);
        h->nboxes = nboxes;
    }
    return h->grp_reach;
}

static int in_union(const Handle *h, int x, int z) {
    for (int i = 0; i < h->nboxes; i++) {
        const int *b = h->boxes + 4 * i;
        if (x >= b[0] && x <= b[2] && z >= b[1] && z <= b[3]) return 1;
    }
    return h->nboxes == 0;
}

static inline int pair_ok(const Handle *h, int x1, int z1, int x2, int z2) {
    int64_t dx = (int64_t)(x1 > x2 ? x1 - x2 : x2 - x1) + h->grp_foot;
    int64_t dz = (int64_t)(z1 > z2 ? z1 - z2 : z2 - z1) + h->grp_foot;
    return dx * dx + dz * dz <= h->grp_d2;
}
EXPORT void sh_stats(void *p, uint64_t *out) { memcpy(out, ((Handle *)p)->st, sizeof(uint64_t) * NSTAT); }
EXPORT void sh_stats_reset(void *p) { memset(((Handle *)p)->st, 0, sizeof(uint64_t) * NSTAT); }

/* Bioma "de la estructura" cuando isViableStructurePos no muestrea ninguno (p. ej. Ruined Portal,
 * Mansion <=1.17): bioma en el centro del chunk de inicio, con el mismo criterio de escala que usa
 * cubiomes para las estructuras de superficie. */
static int fallback_biome(Handle *h, int x, int z) {
    int cx = x >> 4, cz = z >> 4;
    if (h->dim == DIM_NETHER) return getBiomeAt(&h->g, 4, cx * 4 + 2, 0, cz * 4 + 2);
    if (h->dim == DIM_END)    return getBiomeAt(&h->g, 16, cx, 0, cz);
    return getBiomeAt(&h->g, 4, cx * 4 + 2, h->mc >= MC_1_18 ? (319 >> 2) : 0, cz * 4 + 2);
}

/* Escanea un rectangulo de regiones [rx0..rx1] x [rz0..rz1] (inclusivo). Solo se registran posiciones
 * dentro de la caja [minx..maxx] x [minz..maxz] (bloques, inclusivo). 'mask' (MASKN bytes, o NULL =
 * cualquier bioma valido) marca los biomas elegidos por el usuario: es un filtro ADICIONAL, nunca
 * sustituye a isViableStructurePos. Escribe triples (x, z, biomaId). Devuelve n, o -1 si 'out' se llena. */
/* ============================== Prefiltro de clima (1.18+) ==============================
 * En 1.18+ el bioma sale del VECINO MAS CERCANO en un espacio de 6 parametros (temperatura, humedad,
 * continentalidad, erosion, profundidad, rareza): cada hoja del arbol de clima es un hiperrectangulo con un bioma.
 * Calcular el bioma completo cuesta ~7 ruidos + un spline + la busqueda en el arbol. El prefiltro calcula los
 * parametros de a uno (los mas selectivos primero) y corta en cuanto es IMPOSIBLE que gane una hoja de los biomas
 * buscados:
 *   - Las hojas de superficie (profundidad 0, y su gemela en profundidad 1) cubren por completo una caja D de
 *     clima (lo verifica tests: t_clima_cobertura). Entonces para cualquier punto p existe una hoja r' que
 *     contiene clamp(p, D): su distancia es exactamente sum_i ex_i^2 (+ termino de profundidad), donde ex_i es lo
 *     que p se sale de D en el parametro i.
 *   - Una hoja buscada s (de superficie) tiene distancia >= sum_{conocidos} d_i(s)^2 + sum_{desconocidos} ex_i^2
 *     (+ el mismo termino de profundidad).
 *   - Si para TODAS las hojas buscadas sum_{conocidos} d_i(s)^2 > sum_{conocidos} ex_i^2, ninguna puede ganarle a
 *     r': el resultado no es un bioma buscado. Es una cota exacta, no una heuristica.
 * Solo se aplica a estructuras cuya viabilidad en 1.18+ es un unico getBiomeAt en (chunk*4+2, chunk*4+2)
 * comparado con isViableFeatureBiome (Witch Hut, piramides, iglu, ruinas oceanicas, naufragios, tesoros, trail
 * ruins). Las que pasan el prefiltro se validan normalmente con isViableStructurePos. */
typedef struct { const uint32_t *steps; const int32_t *param; const uint64_t *nodes; uint32_t order, len; } Arbol;
#define ARBOL(n) { n##_steps, &n##_param[0][0], n##_nodes, n##_order, sizeof(n##_nodes) / sizeof(uint64_t) }

static const Arbol *arbol_clima(int mc) {      /* misma seleccion que climateToBiome() */
    static const Arbol a18 = ARBOL(btree18), a192 = ARBOL(btree192), a19 = ARBOL(btree19), a20 = ARBOL(btree20),
                       a21wd = ARBOL(btree21wd), a215 = ARBOL(btree215), a262 = ARBOL(btree262), a263 = ARBOL(btree263);
    if (mc >= MC_26_3) return &a263;
    if (mc >= MC_26_2) return &a262;
    if (mc >= MC_1_21_5) return &a215;
    if (mc >= MC_1_21_4) return &a21wd;
    if (mc >= MC_1_20_6) return &a20;
    if (mc >= MC_1_19_4) return &a19;
    if (mc >= MC_1_19_2) return &a192;
    return &a18;
}

/* Recorre las hojas igual que get_resulting_node() (incluido el salto de niveles). */
typedef struct { int n, cap; uint64_t *hojas; } Hojas;
static void juntar_hojas(const Arbol *a, int idx, int depth, Hojas *o) {
    if (a->steps[depth] == 0) {
        if (o->n < o->cap) o->hojas[o->n] = a->nodes[idx];
        o->n++;
        return;
    }
    uint32_t step;
    do { step = a->steps[depth]; depth++; } while (idx + step >= a->len);
    uint16_t inner = (uint16_t)(a->nodes[idx] >> 48);
    for (uint32_t i = 0; i < a->order; i++) {
        juntar_hojas(a, inner, depth, o);
        inner += step;
        if (inner >= a->len) break;
    }
}
static inline int32_t hoja_lo(const Arbol *a, uint64_t nd, int np) { return a->param[2 * ((nd >> 8 * np) & 0xFF)]; }
static inline int32_t hoja_hi(const Arbol *a, uint64_t nd, int np) { return a->param[2 * ((nd >> 8 * np) & 0xFF) + 1]; }
static const int NP_CLIMA[5] = { NP_TEMPERATURE, NP_HUMIDITY, NP_CONTINENTALNESS, NP_EROSION, NP_WEIRDNESS };

/* Para tests: hojas del arbol de esa version. out = n x 13 ints (bioma, 6 x [min,max] en orden NP_*). */
EXPORT int sh_climate_leaves(int mc, int32_t *out, int maxn) {
    const Arbol *a = arbol_clima(mc);
    Hojas o = { 0, (int)a->len, (uint64_t *)malloc(sizeof(uint64_t) * a->len) };
    if (!o.hojas) return -1;
    juntar_hojas(a, 0, 0, &o);
    int n = o.n < maxn ? o.n : maxn;
    for (int i = 0; i < n; i++) {
        uint64_t nd = o.hojas[i];
        out[13 * i] = (int32_t)((nd >> 48) & 0xFF);
        for (int p = 0; p < 6; p++) { out[13 * i + 1 + 2 * p] = hoja_lo(a, nd, p); out[13 * i + 2 + 2 * p] = hoja_hi(a, nd, p); }
    }
    free(o.hojas);
    return o.n;
}

static int cmp_iv(const void *x, const void *y) {
    const int32_t *a = (const int32_t *)x, *b = (const int32_t *)y;
    return (a[0] > b[0]) - (a[0] < b[0]);
}
/* Une intervalos (en el lugar): deja m intervalos disjuntos ordenados al principio y devuelve m. */
static int unir(int32_t (*iv)[2], int n) {
    if (n == 0) return 0;
    qsort(iv, n, sizeof(int32_t) * 2, cmp_iv);
    int m = 0;
    for (int i = 1; i < n; i++) {
        if (iv[i][0] <= iv[m][1] + 1) { if (iv[i][1] > iv[m][1]) iv[m][1] = iv[i][1]; }
        else { m++; iv[m][0] = iv[i][0]; iv[m][1] = iv[i][1]; }
    }
    return m + 1;
}

/* on=0 apaga. mask = biomas elegidos por el usuario (o NULL). Devuelve cantidad de hojas buscadas (>=0),
 * -1 si no aplica (version/estructura/dimension), -2 si hay hojas buscadas que no son de superficie. */
EXPORT int sh_set_climate(void *p, int on, const unsigned char *mask) {
    Handle *h = (Handle *)p;
    h->pf_on = 0; h->pf_n = 0;
    if (!on) return 0;
    if (h->dim != DIM_OVERWORLD || h->mc < MC_1_18) return -1;
    switch (h->stype) {
    case Desert_Pyramid: case Jungle_Pyramid: case Swamp_Hut: case Igloo:
    case Ocean_Ruin: case Shipwreck: case Treasure: break;
    case Trail_Ruins: if (h->mc <= MC_1_19) return -1; break;
    default: return -1;
    }
    const Arbol *a = arbol_clima(h->mc);
    Hojas o = { 0, (int)a->len, (uint64_t *)malloc(sizeof(uint64_t) * a->len) };
    if (!o.hojas) return -1;
    juntar_hojas(a, 0, 0, &o);
    int32_t lo[5], hi[5];
    for (int k = 0; k < 5; k++) { lo[k] = INT32_MAX; hi[k] = INT32_MIN; }
    int ns = 0;
    for (int i = 0; i < o.n; i++) {
        uint64_t nd = o.hojas[i];
        int b = (int)((nd >> 48) & 0xFF);
        int32_t d0 = hoja_lo(a, nd, NP_DEPTH), d1 = hoja_hi(a, nd, NP_DEPTH);
        int superficie = (d0 == d1) && (d0 == 0 || d0 == 10000);
        if (superficie && d0 == 0)
            for (int k = 0; k < 5; k++) {
                if (hoja_lo(a, nd, NP_CLIMA[k]) < lo[k]) lo[k] = hoja_lo(a, nd, NP_CLIMA[k]);
                if (hoja_hi(a, nd, NP_CLIMA[k]) > hi[k]) hi[k] = hoja_hi(a, nd, NP_CLIMA[k]);
            }
        if (isViableFeatureBiome(h->mc, h->stype, b) && (!mask || (b < MASKN && mask[b]))) {
            if (!superficie) { free(o.hojas); return -2; }
            o.hojas[ns++] = nd;                     /* compactar las buscadas al principio (i >= ns) */
        }
    }
    /* union de intervalos por parametro; orden: primero donde los buscados ocupan menos parte del dominio */
    double frac[5];
    int nu[5];
    int32_t (*iv)[2] = (int32_t (*)[2])malloc(sizeof(int32_t) * 2 * 5 * (ns ? ns : 1));
    if (!iv) { free(o.hojas); return -1; }
    for (int k = 0; k < 5; k++) {
        int32_t (*u)[2] = iv + k * (ns ? ns : 1);
        for (int i = 0; i < ns; i++) { u[i][0] = hoja_lo(a, o.hojas[i], NP_CLIMA[k]); u[i][1] = hoja_hi(a, o.hojas[i], NP_CLIMA[k]); }
        nu[k] = unir(u, ns);
        int64_t largo = 0;
        for (int i = 0; i < nu[k]; i++) largo += (int64_t)u[i][1] - u[i][0] + 1;
        frac[k] = (double)largo / (double)((int64_t)hi[k] - lo[k] + 1);
    }
    int ord[5] = { 0, 1, 2, 3, 4 };
    for (int i = 1; i < 5; i++)
        for (int j = i; j > 0 && frac[ord[j]] < frac[ord[j - 1]]; j--) { int t = ord[j]; ord[j] = ord[j - 1]; ord[j - 1] = t; }
    free(h->pf_rect); free(h->pf_acc); free(h->pf_union);
    h->pf_rect = (int32_t *)malloc(sizeof(int32_t) * 10 * (ns ? ns : 1));
    h->pf_acc = (int64_t *)malloc(sizeof(int64_t) * (ns ? ns : 1));
    h->pf_union = (int32_t *)malloc(sizeof(int32_t) * 2 * 5 * (ns ? ns : 1));
    if (!h->pf_rect || !h->pf_acc || !h->pf_union) { free(o.hojas); free(iv); return -1; }
    int off = 0;
    for (int k = 0; k < 5; k++) {
        int np = NP_CLIMA[ord[k]];
        h->pf_ord[k] = np;
        h->pf_lo[k] = lo[ord[k]]; h->pf_hi[k] = hi[ord[k]];
        for (int i = 0; i < ns; i++) {
            h->pf_rect[(i * 5 + k) * 2] = hoja_lo(a, o.hojas[i], np);
            h->pf_rect[(i * 5 + k) * 2 + 1] = hoja_hi(a, o.hojas[i], np);
        }
        h->pf_uoff[k] = off;
        int32_t (*u)[2] = iv + ord[k] * (ns ? ns : 1);
        for (int i = 0; i < nu[ord[k]]; i++, off++) { h->pf_union[2 * off] = u[i][0]; h->pf_union[2 * off + 1] = u[i][1]; }
    }
    h->pf_uoff[5] = off;
    free(iv);
    free(o.hojas);
    h->pf_n = ns;
    h->pf_on = 1;
    return ns;
}

/* 1 = puede ser un bioma buscado (hay que calcularlo); 0 = imposible. (x4, z4) en escala 1:4. */
static int clima_posible(Handle *h, int x4, int z4) {
    const BiomeNoise *bn = &h->g.bn;
    const int n = h->pf_n;
    if (n == 0) return 0;
    double px = x4, pz = z4;                    /* igual que sampleBiomeNoise() */
    px += sampleDoublePerlin(&bn->climate[NP_SHIFT], x4, 0, z4) * 4.0;
    pz += sampleDoublePerlin(&bn->climate[NP_SHIFT], z4, x4, 0) * 4.0;
    /* Etapa barata: min_s sum_k d_k(s)^2 >= sum_k min_s d_k(s)^2 = sum_k dist(q_k, union_k)^2. Si ya esa
     * cota supera ex, ninguna hoja buscada puede ganar. Se descarta en cuanto la cota lo permite (casi siempre en
     * el 1er o 2do parametro), asi que la mayoria de las posiciones cuestan 2 ruidos de desplazamiento + 1 o 2
     * de clima en vez de ~7 ruidos + spline + arbol. */
    int64_t q[5], ex = 0, lb = 0;
    for (int k = 0; k < 5; k++) {
        float v = (float)sampleDoublePerlin(&bn->climate[h->pf_ord[k]], px, 0, pz);
        q[k] = (int64_t)(10000.0F * v);
        int64_t e = q[k] < h->pf_lo[k] ? h->pf_lo[k] - q[k] : (q[k] > h->pf_hi[k] ? q[k] - h->pf_hi[k] : 0);
        ex += e * e;
        int64_t du = INT64_MAX;
        for (int i = h->pf_uoff[k]; i < h->pf_uoff[k + 1]; i++) {
            int64_t a0 = h->pf_union[2 * i], a1 = h->pf_union[2 * i + 1];
            int64_t d = q[k] < a0 ? a0 - q[k] : (q[k] > a1 ? q[k] - a1 : 0);
            if (d < du) du = d;
            if (d == 0) break;
        }
        lb += du * du;
        if (lb > ex) return 0;
    }
    /* Etapa exacta (una sola pasada por las hojas): alguna hoja buscada con distancia conocida <= ex. */
    const int32_t *r = h->pf_rect;
    for (int i = 0; i < n; i++, r += 10) {
        int64_t s = 0;
        for (int k = 0; k < 5 && s <= ex; k++) {
            int64_t d = q[k] < r[2 * k] ? r[2 * k] - q[k] : (q[k] > r[2 * k + 1] ? q[k] - r[2 * k + 1] : 0);
            s += d * d;
        }
        if (s <= ex) return 1;
    }
    return 0;
}

/* Validacion completa de una posicion: (2) reglas del juego + (3) filtro de biomas + terreno.
 * Devuelve 1 si la estructura existe (y pasa el filtro) y deja su bioma en *bid. */
static int evaluar(Handle *h, int x, int z, const unsigned char *mask, int need_terrain, int *bid_out) {
    if (h->pf_on && !clima_posible(h, (x >> 4) * 4 + 2, (z >> 4) * 4 + 2)) { h->st[ST_CLIMATE_REJ]++; return 0; }
    h->g.cb_last_biome = -2;
    h->st[ST_VIABLE_CALLS]++;
    int v = isViableStructurePos(h->stype, &h->g, x, z, 0);
    if (!v) return 0;
    h->st[ST_VIABLE_OK]++;
    int bid;
    if (h->stype == Village || h->stype == End_City) bid = v;           /* estos devuelven su bioma */
    else if (h->stype != Fortress && h->g.cb_last_biome >= 0) bid = h->g.cb_last_biome;
    else bid = fallback_biome(h, x, z);
    if (mask && (bid < 0 || bid >= MASKN || !mask[bid])) { h->st[ST_MASK_REJ]++; return 0; }
    if (need_terrain) {
        h->st[ST_TERRAIN_CALLS]++;
        if (!isViableStructureTerrain(h->stype, &h->g, x, z)) return 0;
    }
    if (h->stype == End_City && !isViableEndCityTerrain(&h->g, &h->sn, x, z)) return 0;
    *bid_out = bid;
    return 1;
}

static int ventana(Handle *h, int n) {
    if (n <= h->wcap) return 1;
    free(h->wx); free(h->wz); free(h->wb); free(h->ws);
    h->wx = (int *)malloc(sizeof(int) * n); h->wz = (int *)malloc(sizeof(int) * n);
    h->wb = (int *)malloc(sizeof(int) * n); h->ws = (signed char *)malloc(n);
    if (!h->wx || !h->wz || !h->wb || !h->ws) { h->wcap = 0; return 0; }
    h->wcap = n;
    return 1;
}

/* Modo grupos. Ventana = tile + 'reach' regiones de halo. Solo se consulta el bioma (lo caro) de las
 * posiciones que tienen alguna vecina geometricamente posible, y las vecinas se validan bajo demanda
 * (memoizado dentro del tile). Resultado identico a "escanear todo y despues limpiar las aisladas". */
static int scan_groups(Handle *h, int rx0, int rz0, int rx1, int rz1,
                       int minx, int minz, int maxx, int maxz,
                       const unsigned char *mask, int need_terrain, int *out, int maxn) {
    const int k = h->grp_reach;
    const int W = rx1 - rx0 + 1 + 2 * k, H = rz1 - rz0 + 1 + 2 * k;
    if (!ventana(h, W * H)) return -2;
    int *wx = h->wx, *wz = h->wz, *wb = h->wb;
    signed char *ws = h->ws;
    for (int j = 0; j < H; j++) {                                             /* (1) posiciones: barato */
        for (int i = 0; i < W; i++) {
            int idx = j * W + i;
            Pos pos;
            if (!getStructurePos(h->stype, h->mc, h->seed, rx0 - k + i, rz0 - k + j, &pos)) { ws[idx] = W_NOPOS; continue; }
            wx[idx] = pos.x; wz[idx] = pos.z;
            ws[idx] = in_union(h, pos.x, pos.z) ? W_UNK : W_OUT;
        }
    }
    int n = 0;
    uint64_t positions = 0, in_box = 0, skip = 0;
    for (int j = k; j < H - k; j++) {
        for (int i = k; i < W - k; i++) {
            int idx = j * W + i;
            if (ws[idx] == W_NOPOS) continue;
            positions++;
            int x = wx[idx], z = wz[idx];
            if (x < minx || x > maxx || z < minz || z > maxz || ws[idx] == W_OUT) continue;
            in_box++;
            if (ws[idx] == W_BAD) continue;                                   /* ya validada (como vecina) y no sirve */
            int cand = 0;                                                     /* prefiltro geometrico */
            for (int dj = -k; dj <= k && !cand; dj++)
                for (int di = -k; di <= k; di++) {
                    if (!di && !dj) continue;
                    int q = (j + dj) * W + (i + di);
                    if (W_USABLE(ws[q]) && pair_ok(h, x, z, wx[q], wz[q])) { cand = 1; break; }
                }
            if (!cand) { skip++; continue; }
            if (ws[idx] == W_UNK) ws[idx] = evaluar(h, x, z, mask, need_terrain, &wb[idx]) ? W_OK : W_BAD;
            if (ws[idx] != W_OK) continue;
            int par = 0;                                                      /* vecina valida de verdad */
            for (int dj = -k; dj <= k && !par; dj++)
                for (int di = -k; di <= k; di++) {
                    if (!di && !dj) continue;
                    int q = (j + dj) * W + (i + di);
                    if (!W_USABLE(ws[q]) || !pair_ok(h, x, z, wx[q], wz[q])) continue;
                    if (ws[q] == W_UNK) {
                        int ii = i + di, jj = j + dj;
                        if (ii < k || ii >= W - k || jj < k || jj >= H - k) h->st[ST_HALO_CALLS]++;
                        ws[q] = evaluar(h, wx[q], wz[q], mask, need_terrain, &wb[q]) ? W_OK : W_BAD;
                    }
                    if (ws[q] == W_OK) { par = 1; break; }
                }
            if (!par) continue;
            if (n >= maxn) return -1;
            out[n * 3] = x; out[n * 3 + 1] = z; out[n * 3 + 2] = wb[idx];
            n++;
        }
    }
    h->st[ST_POSITIONS] += positions; h->st[ST_IN_BOX] += in_box; h->st[ST_GROUP_SKIP] += skip;
    return n;
}

EXPORT int sh_scan_tile(void *p, int rx0, int rz0, int rx1, int rz1,
                        int minx, int minz, int maxx, int maxz,
                        const unsigned char *mask, unsigned flags, int *out, int maxn) {
    Handle *h = (Handle *)p;
    const int need_terrain = (h->dim == DIM_OVERWORLD && h->mc >= MC_1_18 && !(flags & F_NO_TERRAIN));
    int n = 0;
    if ((flags & F_GROUPS) && !(flags & F_NO_VIABLE)) {
        if (h->grp_reach > 0)
            n = scan_groups(h, rx0, rz0, rx1, rz1, minx, minz, maxx, maxz, mask, need_terrain, out, maxn);
        if (n < 0) return n;
    } else {
        uint64_t positions = 0, in_box = 0;
        for (int rz = rz0; rz <= rz1; rz++) {
            for (int rx = rx0; rx <= rx1; rx++) {
                Pos pos;
                if (!getStructurePos(h->stype, h->mc, h->seed, rx, rz, &pos)) continue;   /* (1) posicion */
                positions++;
                if (pos.x < minx || pos.x > maxx || pos.z < minz || pos.z > maxz) continue;
                in_box++;
                if (flags & F_NO_VIABLE) continue;
                int bid;
                if (!evaluar(h, pos.x, pos.z, mask, need_terrain, &bid)) continue;        /* (2)+(3) */
                if (n >= maxn) return -1;
                out[n * 3] = pos.x; out[n * 3 + 1] = pos.z; out[n * 3 + 2] = bid;
                n++;
            }
        }
        h->st[ST_POSITIONS] += positions; h->st[ST_IN_BOX] += in_box;
    }
    h->st[ST_REGIONS] += (uint64_t)(rx1 - rx0 + 1) * (uint64_t)(rz1 - rz0 + 1);
    h->st[ST_FOUND] += (uint64_t)n;
    return n;
}

/* ---- Implementacion ANTERIOR (referencia para el benchmark / test de equivalencia) ---------------
 * Se conserva sin cambios, incluido su criterio de bioma: muestrea en (pos>>2, y=63>>2), que NO es el
 * punto que usa la regla de generacion. */
EXPORT int sh_scan(void *p, int rx0, int rz0, int rx1, int rz1,
                   int minx, int minz, int maxx, int maxz,
                   const unsigned char *mask, int *out, int maxn) {
    Handle *h = (Handle *)p;
    int n = 0;
    int by = (h->dim == 0) ? (63 >> 2) : 0;
    for (int rz = rz0; rz <= rz1; rz++) {
        for (int rx = rx0; rx <= rx1; rx++) {
            Pos pos;
            if (!getStructurePos(h->stype, h->mc, h->seed, rx, rz, &pos)) continue;
            if (pos.x < minx || pos.x > maxx || pos.z < minz || pos.z > maxz) continue;
            if (!isViableStructurePos(h->stype, &h->g, pos.x, pos.z, 0)) continue;
            int bid = getBiomeAt(&h->g, 4, pos.x >> 2, by, pos.z >> 2);
            if (mask && (bid < 0 || bid > 255 || !mask[bid])) continue;
            if (h->dim == 0 && h->mc >= MC_1_18 &&
                !isViableStructureTerrain(h->stype, &h->g, pos.x, pos.z)) continue;
            if (h->stype == End_City &&
                !isViableEndCityTerrain(&h->g, &h->sn, pos.x, pos.z)) continue;
            if (n >= maxn) return n;
            out[n*3] = pos.x; out[n*3+1] = pos.z; out[n*3+2] = bid;
            n++;
        }
    }
    return n;
}
