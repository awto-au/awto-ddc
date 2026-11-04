//--------------------------------------------------
// awto: D3 EDID = scripts/fw_edid_tables.py output (make_edid.py, per-unit serial); docs/edid-fix.md
//--------------------------------------------------
#if((_WRITE_EDID_TO_SYSTEM_EEPROM == _ON) || ((_D3_EMBEDDED_DDCRAM_MAX_SIZE != _EDID_SIZE_NONE) && (_D3_EMBEDDED_DDCRAM_LOCATION == _EDID_TABLE_LOCATION_CODE)))

BYTE code tEDID_TABLE_D3[] =
{
#include "awto_edid_hdmi.h"
};

#endif
