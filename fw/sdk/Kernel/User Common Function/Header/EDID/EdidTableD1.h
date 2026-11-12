//--------------------------------------------------
//--------------------------------------------------
#if((_WRITE_EDID_TO_SYSTEM_EEPROM == _ON) || ((_D1_EMBEDDED_DDCRAM_MAX_SIZE != _EDID_SIZE_NONE) && (_D1_EMBEDDED_DDCRAM_LOCATION == _EDID_TABLE_LOCATION_CODE)))

BYTE __code tEDID_TABLE_D1[] =
{
#include "awto_edid_dp.h"
};

#endif
