#include "chests.h"
#include "n64.h"
#include "gfx.h"

#define BROWN_FRONT_TEXTURE 0x06001798
#define BROWN_BASE_TEXTURE 0x06002798
#define GOLD_FRONT_TEXTURE 0x06002F98
#define GOLD_BASE_TEXTURE 0x06003798

#define CHEST_BASE 1
#define CHEST_LID 3

uint32_t CHEST_TEXTURE_MATCH_CONTENTS = 0;
uint32_t CHEST_SIZE_MATCH_CONTENTS = 0;
uint32_t CHEST_SIZE_TEXTURE = 0;

extern void* GILDED_CHEST_FRONT_TEXTURE;
extern void* GILDED_CHEST_BASE_TEXTURE;
extern void* SILVER_CHEST_FRONT_TEXTURE;
extern void* SILVER_CHEST_BASE_TEXTURE;
extern void* SKULL_CHEST_FRONT_TEXTURE;
extern void* SKULL_CHEST_BASE_TEXTURE;

extern Mtx_t* write_matrix_stack_top(z64_gfx_t* gfx);
asm(".equ write_matrix_stack_top, 0x800AB900");

void get_chest_override(z64_actor_t *actor) {
    uint8_t size  = ((uint8_t*)actor)[0x01E9];
    uint8_t color = size;

    if (CHEST_SIZE_MATCH_CONTENTS || CHEST_SIZE_TEXTURE || CHEST_TEXTURE_MATCH_CONTENTS) {
        uint8_t scene = z64_game.scene_index;
        uint8_t item_id = (actor->variable & 0x0FE0) >> 5;

        override_t override = lookup_override(actor, scene, item_id);
        if (override.value.item_id != 0) {
            // looks_like_item_id is currently limited to 8 bits, so we replace silver rupee pouch cloaks with silver rupee cloaks as a quick fix to make item IDs >= 0x0100 work
            //TODO proper fix
            item_row_t *item_row = get_item_row(((uint16_t) override.value.looks_like_item_id) + (override.value.looks_like_item_id >= 0x00EA ? 0x00EA - 0x00D4 : 0));
            if (item_row == NULL) {
                item_row = get_item_row(override.value.item_id);
            }
            if (CHEST_SIZE_MATCH_CONTENTS || CHEST_SIZE_TEXTURE) {
                if (item_row->chest_type == BROWN_CHEST || item_row->chest_type == SILVER_CHEST || item_row->chest_type == SKULL_CHEST_SMALL) {
                    // Small chest
                    size = 5;
                }
                else {
                    // Big chest
                    size = 0;
                }
            }

            color = item_row->chest_type;
        }
    }

    ((uint8_t*)actor)[0x01EC] = size;
    ((uint8_t*)actor)[0x01ED] = color;
    if (CHEST_LENS_ONLY) {
        // Actor flag 7 makes actors invisible
        // Usually only applies to chest types 4 and 6
        actor->flags |= 0x80;
    }
}

void draw_chest(z64_game_t* game, int part, void* unk, void* unk2,
    z64_actor_t *actor, Gfx **opa_ptr) {
    if (part != CHEST_BASE && part != CHEST_LID)
        return;

    z64_gfx_t *gfx = game->common.gfx;
    int chest_type = ((uint8_t*)actor)[0x01ED];
    if (CHEST_SIZE_MATCH_CONTENTS && chest_type == SILVER_CHEST) {
        chest_type = GOLD_CHEST;
    }

    //write matrix
    Mtx_t *mtx = write_matrix_stack_top(gfx);
    gSPMatrix((*opa_ptr)++, mtx, G_MTX_MODELVIEW | G_MTX_LOAD | G_MTX_NOPUSH);

    int dlist;

    if (part == CHEST_BASE) {
        if (chest_type == GOLD_CHEST)
            dlist = 0x06000AE8;
        else
            dlist = 0x060006F0;

    }
    else { //(part == CHEST_LID)
        if (chest_type == GOLD_CHEST)
            dlist = 0x06001678;
        else
            dlist = 0x060010C0;
    }

    if (chest_type != GOLD_CHEST) {
        //set texture type
        void* frontTexture = (void*)BROWN_FRONT_TEXTURE;
        void* baseTexture = (void*)BROWN_BASE_TEXTURE;

        if (CHEST_SIZE_TEXTURE || CHEST_TEXTURE_MATCH_CONTENTS) {
            if (chest_type == GILDED_CHEST) {
                frontTexture = &GILDED_CHEST_FRONT_TEXTURE;
                baseTexture = &GILDED_CHEST_BASE_TEXTURE;
            }
            else if (chest_type == SILVER_CHEST) {
                frontTexture = &SILVER_CHEST_FRONT_TEXTURE;
                baseTexture = &SILVER_CHEST_BASE_TEXTURE;
            }
            else if (chest_type == SKULL_CHEST_SMALL || chest_type == SKULL_CHEST_BIG) {
                frontTexture = &SKULL_CHEST_FRONT_TEXTURE;
                baseTexture = &SKULL_CHEST_BASE_TEXTURE;
            }
        }

        //the brown chest's base and lid dlist has been modified to jump to
        //segment 09 in order to dynamically set the chest front and base textures
        gfx->poly_opa.d -= 4;
        gDPSetTextureImage(gfx->poly_opa.d, G_IM_FMT_RGBA, G_IM_SIZ_16b, 1, frontTexture);
        gSPEndDisplayList(gfx->poly_opa.d + 1);
        gDPSetTextureImage(gfx->poly_opa.d + 2, G_IM_FMT_RGBA, G_IM_SIZ_16b, 1, baseTexture);
        gSPEndDisplayList(gfx->poly_opa.d + 3);

        gMoveWd((*opa_ptr)++, G_MW_SEGMENT, 9 * sizeof(int), gfx->poly_opa.d);
    }
    gSPDisplayList((*opa_ptr)++, dlist);
}
