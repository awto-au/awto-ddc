# RTD2795T-CG LQFP216 pin ledger

Interactive filtered view: [open the HTML pin ledger](rtd2795t-216-pin-ledger.html).

Interface-specific view: [open the bus explorer](rtd2795t-bus-view.html).

Device capabilities and electrical data: [open the datasheet facts](rtd2795t-datasheet-facts.md).

This is the human-readable view of the RE pin ledger. The JSON file is the canonical machine-readable form;
the TSV is retained for spreadsheet and command-line processing.

Package-table source: [RTD2795T-CG Datasheet, Table 1](https://rtddisplay.com/upload/20231007170054.pdf) (third-party mirror, not an official Realtek host).

Board roles combine the package table with live pin-share state and original-firmware analysis. `—` means that
the field does not apply or the PCB connection has not been traced.

`Realtek QA-B demo use` is the SDK reference selection from `RL6449_QA_B_1A2MHL1DP1mDP_DPTX_eDP`;
it is shown for comparison and is **not** the JXC board pinout. The SDK contains multiple other RL6449 layouts.

## Pins 1–54

| Pin | Datasheet signal | One-line description | Mux? | Scaler GPIO | Live configured function | Closest Realtek QA-B reference function | JXC board use | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | HDMI_HPD/GPIO | HDMI hot-plug output, alternatively an MCU GPIO. | Y | P1.0 | P1D0o<OD> & d3_hdmi_hpd_int<I> | P1D0o<OD> & d3_hdmi_hpd_int<I> | HDMI-2 HPD | confirmed |
| 2 | RX_33V | 3.3 V supply for the HDMI/DP high-speed receiver block. | N | — | — | — | board connection not traced | package-function-only |
| 3 | RXCP_3 | HDMI/DVI TMDS differential clock input. | N | — | — | — | board connection not traced | package-function-only |
| 4 | RXCN_3 | HDMI/DVI TMDS differential clock input. | N | — | — | — | board connection not traced | package-function-only |
| 5 | RX2P_3 | HDMI/DVI TMDS differential data input. | N | — | — | — | board connection not traced | package-function-only |
| 6 | RX2N_3 | HDMI/DVI TMDS differential data input. | N | — | — | — | board connection not traced | package-function-only |
| 7 | TMDS_GND | Ground reference for the HDMI/DVI TMDS receiver. | N | — | — | — | board connection not traced | package-function-only |
| 8 | RX1P_3 | HDMI/DVI TMDS differential data input. | N | — | — | — | board connection not traced | package-function-only |
| 9 | RX1N_3 | HDMI/DVI TMDS differential data input. | N | — | — | — | board connection not traced | package-function-only |
| 10 | TMDS_GND | Ground reference for the HDMI/DVI TMDS receiver. | N | — | — | — | board connection not traced | package-function-only |
| 11 | RX0P_3 | HDMI/DVI TMDS differential data input. | N | — | — | — | board connection not traced | package-function-only |
| 12 | RX0N_3 | HDMI/DVI TMDS differential data input. | N | — | — | — | board connection not traced | package-function-only |
| 13 | GDI_11V | 1.1 V core supply for the high-speed digital input block. | N | — | — | — | board connection not traced | package-function-only |
| 14 | HDMI_HPD/GPIO | HDMI hot-plug output, alternatively an MCU GPIO. | Y | P1.1 | P1D1o<OD> & d2_hdmi_hpd_int<I> | P1D1o<OD> & d2_hdmi_hpd_int<I> | HDMI-1 HPD | confirmed |
| 15 | RX_33V | 3.3 V supply for the HDMI/DP high-speed receiver block. | N | — | — | — | board connection not traced | package-function-only |
| 16 | RXCP_2 | HDMI/DVI TMDS differential clock input. | N | — | — | — | board connection not traced | package-function-only |
| 17 | RXCN_2 | HDMI/DVI TMDS differential clock input. | N | — | — | — | board connection not traced | package-function-only |
| 18 | RX2P_2 | HDMI/DVI TMDS differential data input. | N | — | — | — | board connection not traced | package-function-only |
| 19 | RX2N_2 | HDMI/DVI TMDS differential data input. | N | — | — | — | board connection not traced | package-function-only |
| 20 | TMDS_GND | Ground reference for the HDMI/DVI TMDS receiver. | N | — | — | — | board connection not traced | package-function-only |
| 21 | RX1P_2 | HDMI/DVI TMDS differential data input. | N | — | — | — | board connection not traced | package-function-only |
| 22 | RX1N_2 | HDMI/DVI TMDS differential data input. | N | — | — | — | board connection not traced | package-function-only |
| 23 | TMDS_GND | Ground reference for the HDMI/DVI TMDS receiver. | N | — | — | — | board connection not traced | package-function-only |
| 24 | RX0P_2 | HDMI/DVI TMDS differential data input. | N | — | — | — | board connection not traced | package-function-only |
| 25 | RX0N_2 | HDMI/DVI TMDS differential data input. | N | — | — | — | board connection not traced | package-function-only |
| 26 | GDI_11V | 1.1 V core supply for the high-speed digital input block. | N | — | — | — | board connection not traced | package-function-only |
| 27 | RX_33V | 3.3 V supply for the HDMI/DP high-speed receiver block. | N | — | — | — | board connection not traced | package-function-only |
| 28 | LANE0P_1 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 29 | LANE0N_1 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 30 | DP_GND | Ground reference for DisplayPort receiver lanes. | N | — | — | — | board connection not traced | package-function-only |
| 31 | LANE1P_1 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 32 | LANE1N_1 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 33 | DP_GND | Ground reference for DisplayPort receiver lanes. | N | — | — | — | board connection not traced | package-function-only |
| 34 | LANE2P_1 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 35 | LANE2N_1 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 36 | DP_GND | Ground reference for DisplayPort receiver lanes. | N | — | — | — | board connection not traced | package-function-only |
| 37 | LANE3P_1 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 38 | LANE3N_1 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 39 | DP_GND | Ground reference for DisplayPort receiver lanes. | N | — | — | — | board connection not traced | package-function-only |
| 40 | GDI_11V | 1.1 V core supply for the high-speed digital input block. | N | — | — | — | board connection not traced | package-function-only |
| 41 | LANE0P_0 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 42 | LANE0N_0 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 43 | DP_GND | Ground reference for DisplayPort receiver lanes. | N | — | — | — | board connection not traced | package-function-only |
| 44 | LANE1P_0 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 45 | LANE1N_0 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 46 | DP_GND | Ground reference for DisplayPort receiver lanes. | N | — | — | — | board connection not traced | package-function-only |
| 47 | LANE2P_0 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 48 | LANE2N_0 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 49 | DP_GND | Ground reference for DisplayPort receiver lanes. | N | — | — | — | board connection not traced | package-function-only |
| 50 | LANE3P_0 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 51 | LANE3N_0 | DisplayPort receiver differential lane input. | N | — | — | — | board connection not traced | package-function-only |
| 52 | DP_GND | Ground reference for DisplayPort receiver lanes. | N | — | — | — | board connection not traced | package-function-only |
| 53 | GDI_11V | 1.1 V core supply for the high-speed digital input block. | N | — | — | — | board connection not traced | package-function-only |
| 54 | ADC_VDD33 | 3.3 V supply for the analogue VGA ADC. | N | — | — | — | board connection not traced | package-function-only |

## Pins 55–108

| Pin | Datasheet signal | One-line description | Mux? | Scaler GPIO | Live configured function | Closest Realtek QA-B reference function | JXC board use | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 55 | AVS | Analogue VGA vertical sync input. | N | — | — | — | board connection not traced | package-function-only |
| 56 | AHS | Analogue VGA horizontal sync input. | N | — | — | — | board connection not traced | package-function-only |
| 57 | B- | Negative blue/Pb analogue VGA/component input. | N | — | — | — | board connection not traced | package-function-only |
| 58 | B+ | Positive blue/Pb analogue VGA/component input. | N | — | — | — | board connection not traced | package-function-only |
| 59 | G- | Negative green/Y analogue VGA/component input. | N | — | — | — | board connection not traced | package-function-only |
| 60 | G+ | Positive green/Y analogue VGA/component input. | N | — | — | — | board connection not traced | package-function-only |
| 61 | SOG | Sync-on-green analogue input. | N | — | — | — | board connection not traced | package-function-only |
| 62 | R- | Negative red/Pr analogue VGA/component input. | N | — | — | — | board connection not traced | package-function-only |
| 63 | R+ | Positive red/Pr analogue VGA/component input. | N | — | — | — | board connection not traced | package-function-only |
| 64 | ADC_GND | Ground reference for the analogue VGA ADC. | N | — | — | — | board connection not traced | package-function-only |
| 65 | DDCSCL_VGA/GPIO | VGA DDC clock, alternatively an MCU GPIO. | Y | P1.2 | ddcsclvga<OD> | ddcsclvga<OD> | unused—VGA DDC clock selected, but this board has no VGA connector | confirmed-unused-external |
| 66 | DDCSDA_VGA/GPIO | VGA DDC data, alternatively an MCU GPIO. | Y | P1.3 | ddcsdavga<I> | ddcsdavga<I> | unused—VGA DDC data selected, but this board has no VGA connector | confirmed-unused-external |
| 67 | TCON[1]/GPIO/Test4b | Timing-controller or MCU GPIO pad. | Y | P1.4 | P1D4i<I> | P1D4i<I> | unused GPIO input (reference name VGA cable detect) | inferred |
| 68 | TCON[3]/GPIO/Test4b | Timing-controller or MCU GPIO pad. | Y | P1.5 | P1D5i<I> | P1D5i<I> | unused D0 connector-sense input | inferred |
| 69 | TCON[0]/GPIO/Test4b | Timing-controller or MCU GPIO pad. | Y | P1.6 | P1D6i<I> | P1D6i<I> | unused D0 connector-sense input | inferred |
| 70 | TCON[8]/GPIO/Test4b | Timing-controller or MCU GPIO pad. | Y | P1.7 | P1D7i<I> | P1D7i<I> | unused D0 connector-sense input | inferred |
| 71 | DPTX_HPD/TCON[4]/GPIO | Timing-controller or MCU GPIO pad. | Y | P3.0 | P3D0i<I> | dptx_hpd_org<I> | front-panel POWER key, active low | confirmed |
| 72 | PVCC | 3.3 V digital pad-ring supply. | N | — | — | — | board connection not traced | package-function-only |
| 73 | VCCK_ON | 1.1 V core supply for the on power domain. | N | — | — | — | board connection not traced | package-function-only |
| 74 | AUXP0/GPIO | DisplayPort receiver AUX-channel pin, alternatively an MCU GPIO. | Y | P3.1 | P3D1i<I> | auxp0 | unused D0 AUX/GPIO input | inferred |
| 75 | AUXN0/GPIO | DisplayPort receiver AUX-channel pin, alternatively an MCU GPIO. | Y | P3.2 | P3D2i<I> | auxn0 | unused D0 AUX/GPIO input | inferred |
| 76 | AUXP1/GPIO | DisplayPort receiver AUX-channel pin, alternatively an MCU GPIO. | Y | P3.3 | auxp1 | auxp1 | DisplayPort input AUX+ | confirmed |
| 77 | AUXN1/GPIO | DisplayPort receiver AUX-channel pin, alternatively an MCU GPIO. | Y | P3.4 | auxn1 | auxn1 | DisplayPort input AUX- | confirmed |
| 78 | NC | Not connected in the LQFP216 package. | N | — | — | — | board connection not traced | package-function-only |
| 79 | NC | Not connected in the LQFP216 package. | N | — | — | — | board connection not traced | package-function-only |
| 80 | NC | Not connected in the LQFP216 package. | N | — | — | — | board connection not traced | package-function-only |
| 81 | NC | Not connected in the LQFP216 package. | N | — | — | — | board connection not traced | package-function-only |
| 82 | NC | Not connected in the LQFP216 package. | N | — | — | — | board connection not traced | package-function-only |
| 83 | NC | Not connected in the LQFP216 package. | N | — | — | — | board connection not traced | package-function-only |
| 84 | NC | Not connected in the LQFP216 package. | N | — | — | — | board connection not traced | package-function-only |
| 85 | NC | Not connected in the LQFP216 package. | N | — | — | — | board connection not traced | package-function-only |
| 86 | NC | Not connected in the LQFP216 package. | N | — | — | — | board connection not traced | package-function-only |
| 87 | NC | Not connected in the LQFP216 package. | N | — | — | — | board connection not traced | package-function-only |
| 88 | NC | Not connected in the LQFP216 package. | N | — | — | — | board connection not traced | package-function-only |
| 89 | XI | 14.318 MHz crystal input. | N | — | — | — | board connection not traced | package-function-only |
| 90 | XO | 14.318 MHz crystal output. | N | — | — | — | board connection not traced | package-function-only |
| 91 | GPIO | Timing-controller or MCU GPIO pad. | Y | P3.5 | P3D5o<PP> | dptx_aux_ch_p | front power LED normal/on colour | confirmed-role |
| 92 | GPIO | Timing-controller or MCU GPIO pad. | Y | P3.6 | P3D6o<PP> | dptx_aux_ch_n | front power LED standby colour | confirmed-role |
| 93 | PVCC | 3.3 V digital pad-ring supply. | N | — | — | — | board connection not traced | package-function-only |
| 94 | A-ADC0/INT0/GPIO/Test4b | Five-bit low-speed ADC input for keys/sensors; alternate GPIO. | Y | P3.7 | a_adc0_0 | a_adc0_0 | front-key resistor ladder ADC A0 | confirmed |
| 95 | A-ADC1/INT1/GPIO/Test4b | Five-bit low-speed ADC input for keys/sensors; alternate GPIO. | Y | P4.0 | a_adc1_0 | a_adc1_0 | front-key resistor ladder ADC A1 | confirmed |
| 96 | TCON[9]/A-ADC2/GPIO/Test4b | Five-bit low-speed ADC input for keys/sensors; alternate GPIO. | Y | P4.1 | P4D1i<I> | P4D1o<PP> | unused D0 HPD/GPIO input | inferred |
| 97 | TCON[10]/A-ADC3/GPIO/Test4b | Five-bit low-speed ADC input for keys/sensors; alternate GPIO. | Y | P4.2 | P4D2o<PP> | P4D2o<PP> | DisplayPort input HPD | confirmed |
| 98 | DDR2IO_V18 | 1.8 V DDR2 I/O supply. | N | — | — | — | board connection not traced | package-function-only |
| 99 | DDR2IO_V18 | 1.8 V DDR2 I/O supply. | N | — | — | — | board connection not traced | package-function-only |
| 100 | VCCK_OFF | 1.1 V core supply for the off power domain. | N | — | — | — | board connection not traced | package-function-only |
| 101 | DDR2IO_V18 | 1.8 V DDR2 I/O supply. | N | — | — | — | board connection not traced | package-function-only |
| 102 | DDR2IO_VSS | DDR2 I/O ground. | N | — | — | — | board connection not traced | package-function-only |
| 103 | DDR2_PLL_V33 | 3.3 V DDR2 PLL supply. | N | — | — | — | board connection not traced | package-function-only |
| 104 | VCCK_OFF | 1.1 V core supply for the off power domain. | N | — | — | — | board connection not traced | package-function-only |
| 105 | DDR2IO_V18 | 1.8 V DDR2 I/O supply. | N | — | — | — | board connection not traced | package-function-only |
| 106 | VCCK_OFF | 1.1 V core supply for the off power domain. | N | — | — | — | board connection not traced | package-function-only |
| 107 | DDR2IO_V18 | 1.8 V DDR2 I/O supply. | N | — | — | — | board connection not traced | package-function-only |
| 108 | PGND | Digital pad/DDR2 ground. | N | — | — | — | board connection not traced | package-function-only |

## Pins 109–162

| Pin | Datasheet signal | One-line description | Mux? | Scaler GPIO | Live configured function | Closest Realtek QA-B reference function | JXC board use | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 109 | AUDIO_HOUTL/SD2/SPDIF2/GPIO | Analogue headphone DAC output; alternate digital audio/GPIO. | Y | P4.3 | audio_houtl | audio_houtl | audio headphone DAC left | configured |
| 110 | AUDIO_HOUTR/SD3/SPDIF3/GPIO | Analogue headphone DAC output; alternate digital audio/GPIO. | Y | P4.4 | audio_houtr | audio_houtr | audio headphone DAC right | configured |
| 111 | AUDIO_HP_GND | Analogue ground for the headphone output stage. | N | — | — | — | board connection not traced | package-function-only |
| 112 | AUDIO_HP_AVDD33 | 3.3 V analogue supply for the headphone output stage. | N | — | — | — | board connection not traced | package-function-only |
| 113 | LINE_INL/WS/GPIO | Analogue line input; alternate I2S/GPIO. | Y | P4.5 | P4D5i<I> | line_inl | speaker/headphone selection input | confirmed-role |
| 114 | LINE_INR/SCK/GPIO | Analogue line input; alternate I2S/GPIO. | Y | P4.6 | P4D6i<I> | line_inr | GPIO input; board load unresolved | unknown-load |
| 115 | AUDIO_REF/MCK/GPIO | Audio analogue reference; alternate I2S clock/GPIO. | Y | P4.7 | audio_ref | audio_ref | audio analogue reference | configured |
| 116 | AUDIO_SOUTL/SD0/SPDIF0/GPIO | Analogue speaker DAC output; alternate digital audio/GPIO. | Y | P5.0 | audio_soutl | audio_soutl | audio speaker DAC left | configured |
| 117 | AUDIO_SOUTR/SD1/SPDIF1/GPIO | Analogue speaker DAC output; alternate digital audio/GPIO. | Y | P5.1 | audio_soutr | audio_soutr | audio speaker DAC right | configured |
| 118 | AUDIO_DAC_GND | Analogue ground for the audio DAC. | N | — | — | — | board connection not traced | package-function-only |
| 119 | AUDIO_VDD33 | 3.3 V analogue supply for the audio DAC. | N | — | — | — | board connection not traced | package-function-only |
| 120 | DPTX_LANE_N<7>_2/VTX_TX7N | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 121 | DPTX_LANE_P<7>_2/VTX_TX7P | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 122 | DPTX_VDD11 | 1.1 V supply for the panel DisplayPort transmitter. | N | — | — | — | board connection not traced | package-function-only |
| 123 | DPTX_LANE_N<6>_2/VTX_TX6N | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 124 | DPTX_LANE_P<6>_2/VTX_TX6P | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 125 | DPTX_LANE_N<5>_2/VTX_TX5N | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 126 | DPTX_LANE_P<5>_2/VTX_TX5P | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 127 | DPTX_VDD11 | 1.1 V supply for the panel DisplayPort transmitter. | N | — | — | — | board connection not traced | package-function-only |
| 128 | DPTX_LANE_N<4>_2/VTX_TX4N | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 129 | DPTX_LANE_P<4>_2/VTX_TX4P | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 130 | DPTX_VDD33 | 3.3 V supply for the panel DisplayPort transmitter. | N | — | — | — | board connection not traced | package-function-only |
| 131 | DPTX_LANE_N<3>_1/VTX_TX3N | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 132 | DPTX_LANE_P<3>_1/VTX_TX3P | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 133 | DPTX_VDD11 | 1.1 V supply for the panel DisplayPort transmitter. | N | — | — | — | board connection not traced | package-function-only |
| 134 | DPTX_LANE_N<2>_1/VTX_TX2N | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 135 | DPTX_LANE_P<2>_1/VTX_TX2P | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 136 | DPTX_LANE_N<1>_1/VTX_TX1N | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 137 | DPTX_LANE_P<1>_1/VTX_TX1P | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 138 | DPTX_VDD11 | 1.1 V supply for the panel DisplayPort transmitter. | N | — | — | — | board connection not traced | package-function-only |
| 139 | DPTX_LANE_N<0>_1/VTX_TX0N | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 140 | DPTX_LANE_P<0>_1/VTX_TX0P | Panel transmitter differential lane for eDP or V-by-One. | N | — | — | — | board connection not traced | package-function-only |
| 141 | PVCC | 3.3 V digital pad-ring supply. | N | — | — | — | board connection not traced | package-function-only |
| 142 | VCCK_OFF | 1.1 V core supply for the off power domain. | N | — | — | — | board connection not traced | package-function-only |
| 143 | eDPTX_AUX_CH_P_2/GPIO | Panel eDP AUX-channel pin, alternatively an MCU GPIO. | Y | P5.2 | dptx_aux_ch_p_2 | dptx_aux_ch_p_2 | panel eDP transmitter AUX channel 2 + | configured |
| 144 | eDPTX_AUX_CH_N_2/GPIO | Panel eDP AUX-channel pin, alternatively an MCU GPIO. | Y | P5.3 | dptx_aux_ch_n_2 | dptx_aux_ch_n_2 | panel eDP transmitter AUX channel 2 - | configured |
| 145 | eDPTX_HPD2/VTX_PLL_LOCK/GPIO | Panel eDP hot-plug/lock input, alternatively an MCU GPIO. | Y | P5.4 | dptx_hpd2_org | dptx_hpd2_org | panel eDP transmitter channel 2 HPD | configured |
| 146 | eDPTX_AUX_CH_P_1/GPIO | Panel eDP AUX-channel pin, alternatively an MCU GPIO. | Y | P5.5 | dptx_aux_ch_p_1 | dptx_aux_ch_p_1 | panel eDP transmitter AUX channel 1 + | configured |
| 147 | eDPTX_AUX_CH_N_1/GPIO | Panel eDP AUX-channel pin, alternatively an MCU GPIO. | Y | P5.6 | dptx_aux_ch_n_1 | dptx_aux_ch_n_1 | panel eDP transmitter AUX channel 1 - | configured |
| 148 | eDPTX_HPD1/VTX_PLL_HPD/GPIO | Panel eDP hot-plug/lock input, alternatively an MCU GPIO. | Y | P5.7 | dptx_hpd1_org | dptx_hpd1_org | panel eDP transmitter channel 1 HPD | configured |
| 149 | GPIO/IICSCL_1/TCON[2] | Timing-controller or MCU GPIO pad. | Y | P6.0 | P6D0i<I> | P6D0i<I> | GPIO input; reference name DP5V_ON; board load unresolved | unknown-load |
| 150 | GPIO/IICSDA_1/PWM1 | PWM, timing-controller or MCU GPIO pad. | Y | P6.1 | P6D1i<I> | P6D1o<PP> | GPIO input; board load unresolved | unknown-load |
| 151 | GPIO/PWM2/TCON[3] | PWM, timing-controller or MCU GPIO pad. | Y | P6.2 | P6D2i<I> | P6D2o<PP> | GPIO input; board load unresolved | unknown-load |
| 152 | GPIO/PWM5/TCON[2]/Test4b | PWM, timing-controller or MCU GPIO pad. | Y | P6.3 | P6D3i<I> | P6D3o<PP> | GPIO input; reference name LED4 is not a board role | unknown-load |
| 153 | USB_SPI_CLK/CLKO/GPIO/T0 | SPI control signal for an external USB device/hub; not USB D+/D−. | Y | P6.4 | P6D4i<I> | P6D4o<PP> | GPIO input; board load unresolved | unknown-load |
| 154 | USB_SPI_SI/INT0/GPIO/T1 | SPI control signal for an external USB device/hub; not USB D+/D−. | Y | P6.5 | P6D5i<I> | P6D5o<PP> | GPIO input; board load unresolved | unknown-load |
| 155 | USB_SPI_SO/INT1/GPIO/T2 | SPI control signal for an external USB device/hub; not USB D+/D−. | Y | P6.6 | P6D6i<I> | P6D6o<PP> | GPIO input; board load unresolved | unknown-load |
| 156 | USB_SPI_CEB0/IRQB/GPIO/DVS | SPI control signal for an external USB device/hub; not USB D+/D−. | Y | P6.7 | P6D7i<I> | P6D7o<PP> | GPIO input; board load unresolved | unknown-load |
| 157 | USB_SPI_CEB1/T2EX/GPIO | SPI control signal for an external USB device/hub; not USB D+/D−. | Y | P7.0 | P7D0i<I> | P7D0o<PP> | GPIO input; reference name LED5 is not a board role | unknown-load |
| 158 | WS/TCON[12]/GPIO/Test4b | Timing-controller or MCU GPIO pad. | Y | P7.1 | P7D1i<I> | P7D1o<PP> | GPIO input; board load unresolved | unknown-load |
| 159 | SCK/TCON[13]/GPIO/Test4b | Timing-controller or MCU GPIO pad. | Y | P7.2 | P7D2o<PP> | P7D2o<PP> | panel or switched-peripheral power enable, active high | confirmed-role |
| 160 | MCK/GPIO/Test4b | Timing-controller or MCU GPIO pad. | Y | P7.3 | P7D3o<OD> | P7D3o<PP> | static open-drain low after boot; load unresolved | unknown-load |
| 161 | SPDIF0/SD0/GPIO/PWM0 | PWM, timing-controller or MCU GPIO pad. | Y | P7.4 | P7D4o<OD> | P7D4o<PP> | speaker amplifier enable/mute | confirmed-role |
| 162 | PVCC | 3.3 V digital pad-ring supply. | N | — | — | — | board connection not traced | package-function-only |

## Pins 163–216

| Pin | Datasheet signal | One-line description | Mux? | Scaler GPIO | Live configured function | Closest Realtek QA-B reference function | JXC board use | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 163 | GPIO/TCON[5]/SPDIF1/SD1 | Timing-controller or MCU GPIO pad. | Y | P7.5 | P7D5i<I> | P7D5o<PP> | GPIO input; board load unresolved | unknown-load |
| 164 | GPIO/Cryclk/TCON[1]/SPDIF2/SD2 | Timing-controller or MCU GPIO pad. | Y | P7.6 | P7D6i<I> | P7D6o<PP> | GPIO input; board load unresolved | unknown-load |
| 165 | GPIO/TCON[6]/SPDIF3/SD3 | Timing-controller or MCU GPIO pad. | Y | P7.7 | P7D7i<I> | P7D7o<PP> | GPIO input; board load unresolved | unknown-load |
| 166 | PWM3/GPIO/IVS/TCON[8] | PWM, timing-controller or MCU GPIO pad. | Y | P8.0 | P8D0i<I> | P8D0o<PP> | GPIO input; board load unresolved | unknown-load |
| 167 | DDR2IO_V18 | 1.8 V DDR2 I/O supply. | N | — | — | — | board connection not traced | package-function-only |
| 168 | DDR2IO_V18 | 1.8 V DDR2 I/O supply. | N | — | — | — | board connection not traced | package-function-only |
| 169 | VCCK_OFF | 1.1 V core supply for the off power domain. | N | — | — | — | board connection not traced | package-function-only |
| 170 | DDR2IO_V18 | 1.8 V DDR2 I/O supply. | N | — | — | — | board connection not traced | package-function-only |
| 171 | DDR2IO_VSS | DDR2 I/O ground. | N | — | — | — | board connection not traced | package-function-only |
| 172 | DDR2_PLL_V33 | 3.3 V DDR2 PLL supply. | N | — | — | — | board connection not traced | package-function-only |
| 173 | VCCK_OFF | 1.1 V core supply for the off power domain. | N | — | — | — | board connection not traced | package-function-only |
| 174 | DDR2IO_V18 | 1.8 V DDR2 I/O supply. | N | — | — | — | board connection not traced | package-function-only |
| 175 | VCCK_OFF | 1.1 V core supply for the off power domain. | N | — | — | — | board connection not traced | package-function-only |
| 176 | DDR2IO_V18 | 1.8 V DDR2 I/O supply. | N | — | — | — | board connection not traced | package-function-only |
| 177 | PVCC | 3.3 V digital pad-ring supply. | N | — | — | — | board connection not traced | package-function-only |
| 178 | VCCK_ON | 1.1 V core supply for the on power domain. | N | — | — | — | board connection not traced | package-function-only |
| 179 | GPIO/DHS/Test4b | Timing-controller or MCU GPIO pad. | Y | P8.1 | P8D1o<OD> | P8D1o<OD> | VCCK-off control, left released by original firmware | inferred |
| 180 | GPIO/DENA/Test4b | Timing-controller or MCU GPIO pad. | Y | P8.2 | P8D2i<I> | P8D2o<PP> | GPIO input; reference MHL name does not apply | unknown-load |
| 181 | GPIO/DCLK/Test4b | Timing-controller or MCU GPIO pad. | Y | P8.3 | P8D3i<I> | P8D3o<OD> | GPIO input; reference EDID-WP name not proven | unknown-load |
| 182 | DDR2IO_V18 | 1.8 V DDR2 I/O supply. | N | — | — | — | board connection not traced | package-function-only |
| 183 | PGND/DDR2IO_VSS | Digital pad/DDR2 ground. | N | — | — | — | board connection not traced | package-function-only |
| 184 | GPIO/CLKO/TCON[11]/PWM0 | PWM, timing-controller or MCU GPIO pad. | Y | P8.4 | P8D4o<PP> | P8D4o<PP> | NORMAL-power-state enable; switched high on / low standby; load unresolved | confirmed-behaviour |
| 185 | PWM1/GPIO/IENA/TCON[7] | PWM, timing-controller or MCU GPIO pad. | Y | P8.5 | P8D5o<PP> | P8D5o<PP> | NORMAL-power-state enable; switched high on / low standby; load unresolved | confirmed-behaviour |
| 186 | SPI_CLK | Dedicated external firmware-flash SPI signal. | N | — | — | — | board connection not traced | package-function-only |
| 187 | SPI_SI | Dedicated external firmware-flash SPI signal. | N | — | — | — | board connection not traced | package-function-only |
| 188 | SPI_SO | Dedicated external firmware-flash SPI signal. | N | — | — | — | board connection not traced | package-function-only |
| 189 | SPI_CEB | Dedicated external firmware-flash SPI signal. | N | — | — | — | board connection not traced | package-function-only |
| 190 | FLASH_WP/GPIO | External SPI-flash write-protect control, alternatively GPIO. | Y | P8.6 | P8D6o<PP> | P8D6o<PP> | SPI flash write-protect control | confirmed-role |
| 191 | RESETB | Active-low scaler reset input. | N | — | — | — | board connection not traced | package-function-only |
| 192 | VCCK_ON | 1.1 V core supply for the on power domain. | N | — | — | — | board connection not traced | package-function-only |
| 193 | GPIO/Test4b | Timing-controller or MCU GPIO pad. | Y | P8.7 | P8D7i<I> | P8D7i<I> | GPIO input / probably NC | inferred |
| 194 | PWM2/TCON[6]/IR_RECEIVER/GPIO | Infrared receiver input; alternate PWM/TCON/GPIO. | Y | P9.0 | irda_in | P9D0o<PP> | infrared receiver input | confirmed-role |
| 195 | PWM4/TCON[7]/GPIO/pwm_out | PWM, timing-controller or MCU GPIO pad. | Y | P9.1 | PWM4<PP> | P9D1o<PP> | backlight brightness PWM4 | confirmed-role |
| 196 | TCON[5]/GPIO/Test4b | Timing-controller or MCU GPIO pad. | Y | P9.2 | P9D2o<PP> | P9D2o<OD> | backlight enable, active low | confirmed |
| 197 | TCON[4]/GPIO/Test4b | Timing-controller or MCU GPIO pad. | Y | P9.3 | P9D3i<I> | P9D3o<OD> | GPIO input; board load unresolved | unknown-load |
| 198 | GPIO/IHS/Test4b | Timing-controller or MCU GPIO pad. | Y | P9.4 | P9D4i<I> | P9D4i<I> | HDMI-2 cable detect | confirmed |
| 199 | PWM5/GPIO/pwm_in | PWM, timing-controller or MCU GPIO pad. | Y | P9.5 | P9D5i<I> | P9D5o<PP> | GPIO input; reference LED3 name is not a board role | unknown-load |
| 200 | IICSCL_2/PWM4/TCON[11]/GPIO | PWM, timing-controller or MCU GPIO pad. | Y | P9.6 | P9D6i<I> | P9D6o<OD> | GPIO input; reference DDR-power name not active | inferred |
| 201 | IICSDA_2/PWM3/TCON[0]/GPIO | PWM, timing-controller or MCU GPIO pad. | Y | P9.7 | P9D7o<OD> | P9D7o<PP> | NORMAL-power-state open-drain output; load unresolved | confirmed-behaviour |
| 202 | INT0/UART_TX/GPIO/Test4b | 8051 UART transmit; alternate interrupt/GPIO/TCON. | Y | PA.0 | PAD0o<OD> | PAD0i<I> | NORMAL-power-state open-drain output; load unresolved | confirmed-behaviour |
| 203 | INT1/UART_RX/GPIO/Test4b | 8051 UART receive; alternate interrupt/GPIO/TCON. | Y | PA.1 | PAD1i<I> | PAD1i<I> | GPIO input; board load unresolved | unknown-load |
| 204 | TCON[13]/GPIO/Test4b | Timing-controller or MCU GPIO pad. | Y | PA.2 | PAD2i<I> | PAD2i<I> | HDMI-1 cable detect | confirmed |
| 205 | PVCC | 3.3 V digital pad-ring supply. | N | — | — | — | board connection not traced | package-function-only |
| 206 | TCON[12]/GPIO/Test4b | Timing-controller or MCU GPIO pad. | Y | PA.3 | PAD3i<I> | PAD3i<I> | DisplayPort connector pin 17 sense | confirmed |
| 207 | TCON[10]/GPIO/Test4b | Timing-controller or MCU GPIO pad. | Y | PA.4 | PAD4i<I> | PAD4i<I> | DisplayPort connector pin 15 sense | confirmed |
| 208 | TCON[9]/GPIO/Test4b | Timing-controller or MCU GPIO pad. | Y | PA.5 | PAD5i<I> | PAD5i<I> | DisplayPort connector pin 16 sense | confirmed |
| 209 | EEWD/GPIO | External EEPROM write-disable control, alternatively an MCU GPIO. | Y | PA.6 | PAD6i<I> | PAD6o<OD> | GPIO input; reference EEPROM-WP name not active | inferred |
| 210 | EEI2CSCL/GPIO | External EEPROM I2C clock, alternatively an MCU GPIO. | Y | PA.7 | PAD7i<I> | eeiicscl | GPIO input; external EEPROM clock function not selected | confirmed-config |
| 211 | EEI2CSDA/GPIO | External EEPROM I2C data, alternatively an MCU GPIO. | Y | PB.0 | PBD0i<I> | eeiicsda | GPIO input; external EEPROM data function not selected | confirmed-config |
| 212 | DDCSCL2/GPIO | HDMI/DVI DDC clock, alternatively an MCU GPIO. | Y | PB.1 | ddcscl2 | ddcscl2 | HDMI-1 DDC clock | confirmed |
| 213 | DDCSDA2/GPIO | HDMI/DVI DDC data, alternatively an MCU GPIO. | Y | PB.2 | ddcsda2 | ddcsda2 | HDMI-1 DDC data | confirmed |
| 214 | DDCSCL3/GPIO | HDMI/DVI DDC clock, alternatively an MCU GPIO. | Y | PB.3 | ddcscl3 | ddcscl3 | HDMI-2 DDC clock | confirmed |
| 215 | DDCSDA3/GPIO | HDMI/DVI DDC data, alternatively an MCU GPIO. | Y | PB.4 | ddcsda3 | ddcsda3 | HDMI-2 DDC data | confirmed |
| 216 | TMDS_REXT | External reference resistor for TMDS receiver impedance. | N | — | — | — | board connection not traced | package-function-only |
