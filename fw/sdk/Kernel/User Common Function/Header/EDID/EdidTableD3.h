//--------------------------------------------------
// D3 = D2 table + (index, value) patch pairs (port tag, checksum), applied by UserCommonEdidPatchD3()
//--------------------------------------------------
#if((_WRITE_EDID_TO_SYSTEM_EEPROM == _ON) || ((_D3_EMBEDDED_DDCRAM_MAX_SIZE != _EDID_SIZE_NONE) && (_D3_EMBEDDED_DDCRAM_LOCATION == _EDID_TABLE_LOCATION_CODE)))

BYTE __code tEDID_PATCH_D3[] =
{
#include "awto_edid_hdmi_d3.h"
};

#endif
