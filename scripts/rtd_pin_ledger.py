#!/usr/bin/env python3
"""Build the RTD2795T/RL6449 216-pin package and board evidence ledger.

The datasheet names every package pin.  Firmware exposes pin-share control for
77 multiplexed pads; fixed high-speed, analogue, power, ground, crystal, and NC
pins do not have (and do not need) page-0x10 pin-share assignments.
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "docs/monitors/pinshare-live-AWT26110003.tsv"
OUT = ROOT / "docs/monitors/rtd2795t-216-pin-ledger.tsv"
OUT_JSON = ROOT / "docs/monitors/rtd2795t-216-pin-ledger.json"
OUT_MD = ROOT / "docs/monitors/rtd2795t-216-pin-ledger.md"
OUT_HTML = ROOT / "docs/monitors/rtd2795t-216-pin-ledger.html"
OUT_BUS_HTML = ROOT / "docs/monitors/rtd2795t-bus-view.html"
DATASHEET = "https://rtddisplay.com/upload/20231007170054.pdf"

# RTD2795T-CG datasheet, Table 1 (LQFP216 Signals Pin Assignment).  Names are
# normalized only for whitespace and obvious OCR line-breaks.
PACKAGE_SIGNAL_TEXT = """\
1\tHDMI_HPD / GPIO
2\tRX_33V
3\tRXCP_3
4\tRXCN_3
5\tRX2P_3
6\tRX2N_3
7\tTMDS_GND
8\tRX1P_3
9\tRX1N_3
10\tTMDS_GND
11\tRX0P_3
12\tRX0N_3
13\tGDI_11V
14\tHDMI_HPD / GPIO
15\tRX_33V
16\tRXCP_2
17\tRXCN_2
18\tRX2P_2
19\tRX2N_2
20\tTMDS_GND
21\tRX1P_2
22\tRX1N_2
23\tTMDS_GND
24\tRX0P_2
25\tRX0N_2
26\tGDI_11V
27\tRX_33V
28\tLANE0P_1
29\tLANE0N_1
30\tDP_GND
31\tLANE1P_1
32\tLANE1N_1
33\tDP_GND
34\tLANE2P_1
35\tLANE2N_1
36\tDP_GND
37\tLANE3P_1
38\tLANE3N_1
39\tDP_GND
40\tGDI_11V
41\tLANE0P_0
42\tLANE0N_0
43\tDP_GND
44\tLANE1P_0
45\tLANE1N_0
46\tDP_GND
47\tLANE2P_0
48\tLANE2N_0
49\tDP_GND
50\tLANE3P_0
51\tLANE3N_0
52\tDP_GND
53\tGDI_11V
54\tADC_VDD33
55\tAVS
56\tAHS
57\tB-
58\tB+
59\tG-
60\tG+
61\tSOG
62\tR-
63\tR+
64\tADC_GND
65\tDDCSCL_VGA / GPIO
66\tDDCSDA_VGA / GPIO
67\tTCON[1] / GPIO / Test4b
68\tTCON[3] / GPIO / Test4b
69\tTCON[0] / GPIO / Test4b
70\tTCON[8] / GPIO / Test4b
71\tDPTX_HPD / TCON[4] / GPIO
72\tPVCC
73\tVCCK_ON
74\tAUXP0 / GPIO
75\tAUXN0 / GPIO
76\tAUXP1 / GPIO
77\tAUXN1 / GPIO
78\tNC
79\tNC
80\tNC
81\tNC
82\tNC
83\tNC
84\tNC
85\tNC
86\tNC
87\tNC
88\tNC
89\tXI
90\tXO
91\tGPIO
92\tGPIO
93\tPVCC
94\tA-ADC0 / INT0 / GPIO / Test4b
95\tA-ADC1 / INT1 / GPIO / Test4b
96\tTCON[9] / A-ADC2 / GPIO / Test4b
97\tTCON[10] / A-ADC3 / GPIO / Test4b
98\tDDR2IO_V18
99\tDDR2IO_V18
100\tVCCK_OFF
101\tDDR2IO_V18
102\tDDR2IO_VSS
103\tDDR2_PLL_V33
104\tVCCK_OFF
105\tDDR2IO_V18
106\tVCCK_OFF
107\tDDR2IO_V18
108\tPGND
109\tAUDIO_HOUTL / SD2 / SPDIF2 / GPIO
110\tAUDIO_HOUTR / SD3 / SPDIF3 / GPIO
111\tAUDIO_HP_GND
112\tAUDIO_HP_AVDD33
113\tLINE_INL / WS / GPIO
114\tLINE_INR / SCK / GPIO
115\tAUDIO_REF / MCK / GPIO
116\tAUDIO_SOUTL / SD0 / SPDIF0 / GPIO
117\tAUDIO_SOUTR / SD1 / SPDIF1 / GPIO
118\tAUDIO_DAC_GND
119\tAUDIO_VDD33
120\tDPTX_LANE_N<7>_2 / VTX_TX7N
121\tDPTX_LANE_P<7>_2 / VTX_TX7P
122\tDPTX_VDD11
123\tDPTX_LANE_N<6>_2 / VTX_TX6N
124\tDPTX_LANE_P<6>_2 / VTX_TX6P
125\tDPTX_LANE_N<5>_2 / VTX_TX5N
126\tDPTX_LANE_P<5>_2 / VTX_TX5P
127\tDPTX_VDD11
128\tDPTX_LANE_N<4>_2 / VTX_TX4N
129\tDPTX_LANE_P<4>_2 / VTX_TX4P
130\tDPTX_VDD33
131\tDPTX_LANE_N<3>_1 / VTX_TX3N
132\tDPTX_LANE_P<3>_1 / VTX_TX3P
133\tDPTX_VDD11
134\tDPTX_LANE_N<2>_1 / VTX_TX2N
135\tDPTX_LANE_P<2>_1 / VTX_TX2P
136\tDPTX_LANE_N<1>_1 / VTX_TX1N
137\tDPTX_LANE_P<1>_1 / VTX_TX1P
138\tDPTX_VDD11
139\tDPTX_LANE_N<0>_1 / VTX_TX0N
140\tDPTX_LANE_P<0>_1 / VTX_TX0P
141\tPVCC
142\tVCCK_OFF
143\teDPTX_AUX_CH_P_2 / GPIO
144\teDPTX_AUX_CH_N_2 / GPIO
145\teDPTX_HPD2 / VTX_PLL_LOCK / GPIO
146\teDPTX_AUX_CH_P_1 / GPIO
147\teDPTX_AUX_CH_N_1 / GPIO
148\teDPTX_HPD1 / VTX_PLL_HPD / GPIO
149\tGPIO / IICSCL_1 / TCON[2]
150\tGPIO / IICSDA_1 / PWM1
151\tGPIO / PWM2 / TCON[3]
152\tGPIO / PWM5 / TCON[2] / Test4b
153\tUSB_SPI_CLK / CLKO / GPIO / T0
154\tUSB_SPI_SI / INT0 / GPIO / T1
155\tUSB_SPI_SO / INT1 / GPIO / T2
156\tUSB_SPI_CEB0 / IRQB / GPIO / DVS
157\tUSB_SPI_CEB1 / T2EX / GPIO
158\tWS / TCON[12] / GPIO / Test4b
159\tSCK / TCON[13] / GPIO / Test4b
160\tMCK / GPIO / Test4b
161\tSPDIF0 / SD0 / GPIO / PWM0
162\tPVCC
163\tGPIO / TCON[5] / SPDIF1 / SD1
164\tGPIO / Cryclk / TCON[1] / SPDIF2 / SD2
165\tGPIO / TCON[6] / SPDIF3 / SD3
166\tPWM3 / GPIO / IVS / TCON[8]
167\tDDR2IO_V18
168\tDDR2IO_V18
169\tVCCK_OFF
170\tDDR2IO_V18
171\tDDR2IO_VSS
172\tDDR2_PLL_V33
173\tVCCK_OFF
174\tDDR2IO_V18
175\tVCCK_OFF
176\tDDR2IO_V18
177\tPVCC
178\tVCCK_ON
179\tGPIO / DHS / Test4b
180\tGPIO / DENA / Test4b
181\tGPIO / DCLK / Test4b
182\tDDR2IO_V18
183\tPGND / DDR2IO_VSS
184\tGPIO / CLKO / TCON[11] / PWM0
185\tPWM1 / GPIO / IENA / TCON[7]
186\tSPI_CLK
187\tSPI_SI
188\tSPI_SO
189\tSPI_CEB
190\tFLASH_WP / GPIO
191\tRESETB
192\tVCCK_ON
193\tGPIO / Test4b
194\tPWM2 / TCON[6] / IR_RECEIVER / GPIO
195\tPWM4 / TCON[7] / GPIO / pwm_out
196\tTCON[5] / GPIO / Test4b
197\tTCON[4] / GPIO / Test4b
198\tGPIO / IHS / Test4b
199\tPWM5 / GPIO / pwm_in
200\tIICSCL_2 / PWM4 / TCON[11] / GPIO
201\tIICSDA_2 / PWM3 / TCON[0] / GPIO
202\tINT0 / UART_TX / GPIO / Test4b
203\tINT1 / UART_RX / GPIO / Test4b
204\tTCON[13] / GPIO / Test4b
205\tPVCC
206\tTCON[12] / GPIO / Test4b
207\tTCON[10] / GPIO / Test4b
208\tTCON[9] / GPIO / Test4b
209\tEEWD / GPIO
210\tEEI2CSCL / GPIO
211\tEEI2CSDA / GPIO
212\tDDCSCL2 / GPIO
213\tDDCSDA2 / GPIO
214\tDDCSCL3 / GPIO
215\tDDCSDA3 / GPIO
216\tTMDS_REXT
"""

PACKAGE_SIGNAL = {}
for package_line in PACKAGE_SIGNAL_TEXT.splitlines():
    package_pin, package_name = package_line.split("\t", 1)
    PACKAGE_SIGNAL[int(package_pin)] = re.sub(r"\s*/\s*", "/", package_name)
if set(PACKAGE_SIGNAL) != set(range(1, 217)):
    raise RuntimeError("RTD2795T package table must contain each pin 1..216 exactly once")

# Board roles established by original-firmware access, live pin-share, or the
# selected dedicated peripheral function.  Anything absent stays explicit.
ROLE = {
    1: ("HDMI-2 HPD", "confirmed", "original-fw write audit"),
    14: ("HDMI-1 HPD", "confirmed", "original-fw write audit"),
    65: ("unused—VGA DDC clock selected, but this board has no VGA connector", "confirmed-unused-external", "live pin-share + confirmed board I/O"),
    66: ("unused—VGA DDC data selected, but this board has no VGA connector", "confirmed-unused-external", "live pin-share + confirmed board I/O"),
    67: ("unused GPIO input (reference name VGA cable detect)", "inferred", "live pin-share"),
    68: ("unused D0 connector-sense input", "inferred", "live pin-share + board ports"),
    69: ("unused D0 connector-sense input", "inferred", "live pin-share + board ports"),
    70: ("unused D0 connector-sense input", "inferred", "live pin-share + board ports"),
    71: ("front-panel POWER key, active low", "confirmed", "original-fw read audit"),
    74: ("unused D0 AUX/GPIO input", "inferred", "live pin-share + board ports"),
    75: ("unused D0 AUX/GPIO input", "inferred", "live pin-share + board ports"),
    76: ("DisplayPort input AUX+", "confirmed", "live pin-share + working DP input"),
    77: ("DisplayPort input AUX-", "confirmed", "live pin-share + working DP input"),
    91: ("front power LED normal/on colour", "confirmed-role", "original-fw LED state machine"),
    92: ("front power LED standby colour", "confirmed-role", "original-fw LED state machine"),
    94: ("front-key resistor ladder ADC A0", "confirmed", "original-fw key scan"),
    95: ("front-key resistor ladder ADC A1", "confirmed", "original-fw key scan"),
    96: ("unused D0 HPD/GPIO input", "inferred", "live pin-share + board ports"),
    97: ("DisplayPort input HPD", "confirmed", "original-fw write/read audit"),
    109: ("audio headphone DAC left", "configured", "live dedicated function"),
    110: ("audio headphone DAC right", "configured", "live dedicated function"),
    113: ("speaker/headphone selection input", "confirmed-role", "original-fw audio output selector"),
    114: ("GPIO input; board load unresolved", "unknown-load", "live pin-share"),
    115: ("audio analogue reference", "configured", "live dedicated function"),
    116: ("audio speaker DAC left", "configured", "live dedicated function"),
    117: ("audio speaker DAC right", "configured", "live dedicated function"),
    143: ("panel eDP transmitter AUX channel 2 +", "configured", "live dedicated function"),
    144: ("panel eDP transmitter AUX channel 2 -", "configured", "live dedicated function"),
    145: ("panel eDP transmitter channel 2 HPD", "configured", "live dedicated function"),
    146: ("panel eDP transmitter AUX channel 1 +", "configured", "live dedicated function"),
    147: ("panel eDP transmitter AUX channel 1 -", "configured", "live dedicated function"),
    148: ("panel eDP transmitter channel 1 HPD", "configured", "live dedicated function"),
    149: ("GPIO input; reference name DP5V_ON; board load unresolved", "unknown-load", "live pin-share"),
    150: ("GPIO input; board load unresolved", "unknown-load", "live pin-share"),
    151: ("GPIO input; board load unresolved", "unknown-load", "live pin-share"),
    152: ("GPIO input; reference name LED4 is not a board role", "unknown-load", "live pin-share"),
    153: ("GPIO input; board load unresolved", "unknown-load", "live pin-share"),
    154: ("GPIO input; board load unresolved", "unknown-load", "live pin-share"),
    155: ("GPIO input; board load unresolved", "unknown-load", "live pin-share"),
    156: ("GPIO input; board load unresolved", "unknown-load", "live pin-share"),
    157: ("GPIO input; reference name LED5 is not a board role", "unknown-load", "live pin-share"),
    158: ("GPIO input; board load unresolved", "unknown-load", "live pin-share"),
    159: ("panel or switched-peripheral power enable, active high", "confirmed-role", "original-fw power sequence + live levels"),
    160: ("static open-drain low after boot; load unresolved", "unknown-load", "original-fw write audit"),
    161: ("speaker amplifier enable/mute", "confirmed-role", "original-fw audio mute procedure"),
    163: ("GPIO input; board load unresolved", "unknown-load", "live pin-share"),
    164: ("GPIO input; board load unresolved", "unknown-load", "live pin-share"),
    165: ("GPIO input; board load unresolved", "unknown-load", "live pin-share"),
    166: ("GPIO input; board load unresolved", "unknown-load", "live pin-share"),
    179: ("VCCK-off control, left released by original firmware", "inferred", "SDK role + original-fw no-write audit"),
    180: ("GPIO input; reference MHL name does not apply", "unknown-load", "live pin-share"),
    181: ("GPIO input; reference EDID-WP name not proven", "unknown-load", "live pin-share"),
    184: ("NORMAL-power-state enable; switched high on / low standby; load unresolved", "confirmed-behaviour", "original-fw power sequence + live levels"),
    185: ("NORMAL-power-state enable; switched high on / low standby; load unresolved", "confirmed-behaviour", "original-fw power sequence + live levels"),
    190: ("SPI flash write-protect control", "confirmed-role", "original-fw flash command audit"),
    193: ("GPIO input / probably NC", "inferred", "live pin-share"),
    194: ("infrared receiver input", "confirmed-role", "original-fw IR decoder path"),
    195: ("backlight brightness PWM4", "confirmed-role", "live PWM4 function + power audit"),
    196: ("backlight enable, active low", "confirmed", "original-fw power sequence + live poke"),
    197: ("GPIO input; board load unresolved", "unknown-load", "live pin-share"),
    198: ("HDMI-2 cable detect", "confirmed", "original-fw read audit"),
    199: ("GPIO input; reference LED3 name is not a board role", "unknown-load", "live pin-share"),
    200: ("GPIO input; reference DDR-power name not active", "inferred", "live pin-share + no-write audit"),
    201: ("NORMAL-power-state open-drain output; load unresolved", "confirmed-behaviour", "original-fw power sequence + live levels"),
    202: ("NORMAL-power-state open-drain output; load unresolved", "confirmed-behaviour", "original-fw power sequence + live levels"),
    203: ("GPIO input; board load unresolved", "unknown-load", "live pin-share"),
    204: ("HDMI-1 cable detect", "confirmed", "original-fw read audit"),
    206: ("DisplayPort connector pin 17 sense", "confirmed", "original-fw cable-detect audit"),
    207: ("DisplayPort connector pin 15 sense", "confirmed", "original-fw cable-detect audit"),
    208: ("DisplayPort connector pin 16 sense", "confirmed", "original-fw cable-detect audit"),
    209: ("GPIO input; reference EEPROM-WP name not active", "inferred", "live pin-share + no-write audit"),
    210: ("GPIO input; external EEPROM clock function not selected", "confirmed-config", "live pin-share"),
    211: ("GPIO input; external EEPROM data function not selected", "confirmed-config", "live pin-share"),
    212: ("HDMI-1 DDC clock", "confirmed", "live DDC2 function + working HDMI-1"),
    213: ("HDMI-1 DDC data", "confirmed", "live DDC2 function + working HDMI-1"),
    214: ("HDMI-2 DDC clock", "confirmed", "live DDC3 function + working HDMI-2"),
    215: ("HDMI-2 DDC data", "confirmed", "live DDC3 function + working HDMI-2"),
}

POWER_RE = re.compile(r"(?:^|[/_ ])(?:VDD|VSS|VCC|PVCC|PGND|GND|AVDD|33V|11V|18)(?:$|[/_ 0-9])", re.I)


def bus_groups(signal: str) -> list[str]:
    """Return every functional interface a multiplexed package signal belongs to."""
    groups = []

    def add(name: str) -> None:
        if name not in groups:
            groups.append(name)

    if signal == "NC":
        add("NC")
    if POWER_RE.search(signal):
        add("Power / ground")
    if re.search(r"HDMI_HPD|RX[0-2CPN]|TMDS|DDCS(?:CL|DA)[23]", signal):
        add("HDMI / DVI")
    if re.search(r"^LANE[0-3][PN]_[01]$|^AUX[PN][01]", signal):
        add("DisplayPort input")
    if re.search(r"DPTX_LANE|DPTX_HPD|eDPTX_", signal):
        add("Panel eDP / V-by-One")
    if re.search(r"^(?:AVS|AHS|[BRG][+-]|SOG|ADC_VDD33|ADC_GND)$|DDCS.._VGA", signal):
        add("VGA / analogue")
    if re.search(r"AUDIO_|LINE_IN|\b(?:WS|SCK|MCK|SD[0-3]|SPDIF[0-3])\b", signal):
        add("Audio / I2S / SPDIF")
    if "USB_SPI" in signal:
        add("USB-SPI")
    if re.search(r"^SPI_|FLASH_WP", signal):
        add("SPI flash")
    if re.search(r"DDCS|IICS|EEI2C|EEWD", signal):
        add("DDC / I2C / EEPROM")
    if "TCON" in signal or re.search(r"\b(?:DHS|DENA|DCLK|IHS|IVS|IENA)\b", signal):
        add("TCON / panel timing")
    if "GPIO" in signal:
        add("GPIO")
    if "PWM" in signal or "pwm_" in signal:
        add("PWM")
    if "A-ADC" in signal:
        add("Key ADC")
    if "IR_RECEIVER" in signal:
        add("IR receiver")
    if "UART" in signal:
        add("UART")
    if signal in ("XI", "XO") or "CLKO" in signal or "Cryclk" in signal:
        add("Clock / crystal")
    if signal == "RESETB":
        add("Reset")
    return groups or ["Other fixed function"]


def pin_description(pin: int, signal: str) -> tuple[str, str, str]:
    """Human-readable package-table summary, expanded description and electrical note."""
    electrical = "See the RTD2795T-CG datasheet electrical tables before probing or driving this pin."
    if signal == "NC":
        return ("Not connected in the LQFP216 package.",
                "The package table marks this lead NC; it has no documented scaler function.",
                "Leave unconnected unless board evidence proves otherwise.")
    if signal == "HDMI_HPD/GPIO":
        summary = "HDMI hot-plug output, alternatively an MCU GPIO."
    elif signal == "RX_33V":
        summary = "3.3 V supply for the HDMI/DP high-speed receiver block."
        electrical = "Nominal 3.3 V supply."
    elif re.match(r"RXC[PN]_", signal):
        summary = "HDMI/DVI TMDS differential clock input."
    elif re.match(r"RX[0-2][PN]_", signal):
        summary = "HDMI/DVI TMDS differential data input."
    elif signal == "TMDS_GND":
        summary = "Ground reference for the HDMI/DVI TMDS receiver."
        electrical = "Analogue ground; preserve the high-speed return path."
    elif signal == "TMDS_REXT":
        summary = "External reference resistor for TMDS receiver impedance."
        electrical = "Datasheet specifies a 12 kΩ reference resistor to ground."
    elif signal == "GDI_11V":
        summary = "1.1 V core supply for the high-speed digital input block."
        electrical = "Nominal 1.1 V supply."
    elif re.match(r"LANE[0-3][PN]_[01]$", signal):
        summary = "DisplayPort receiver differential lane input."
    elif signal == "DP_GND":
        summary = "Ground reference for DisplayPort receiver lanes."
        electrical = "Analogue ground; preserve the high-speed return path."
    elif signal == "ADC_VDD33":
        summary = "3.3 V supply for the analogue VGA ADC."
        electrical = "Nominal 3.3 V supply."
    elif signal in ("AVS", "AHS"):
        summary = f"Analogue VGA {'vertical' if signal == 'AVS' else 'horizontal'} sync input."
        electrical = "Datasheet identifies 5 V tolerance when powered off."
    elif signal in ("B-", "B+", "G-", "G+", "R-", "R+"):
        polarity = "negative" if signal.endswith("-") else "positive"
        colour = {"B": "blue/Pb", "G": "green/Y", "R": "red/Pr"}[signal[0]]
        summary = f"{polarity.capitalize()} {colour} analogue VGA/component input."
        electrical = "Datasheet note: 3.3 V tolerance."
    elif signal == "SOG":
        summary = "Sync-on-green analogue input."
        electrical = "Datasheet note: 3.3 V tolerance."
    elif signal == "ADC_GND":
        summary = "Ground reference for the analogue VGA ADC."
        electrical = "Analogue ground."
    elif signal.startswith("DDCSCL_VGA"):
        summary = "VGA DDC clock, alternatively an MCU GPIO."
    elif signal.startswith("DDCSDA_VGA"):
        summary = "VGA DDC data, alternatively an MCU GPIO."
    elif re.match(r"AUX[PN][01]", signal):
        summary = "DisplayPort receiver AUX-channel pin, alternatively an MCU GPIO."
    elif signal in ("XI", "XO"):
        summary = f"14.318 MHz crystal {'input' if signal == 'XI' else 'output'}."
        electrical = "Datasheet note: 3.3 V tolerance."
    elif signal == "PVCC":
        summary = "3.3 V digital pad-ring supply."
        electrical = "Nominal 3.3 V supply."
    elif signal in ("VCCK_ON", "VCCK_OFF"):
        summary = f"1.1 V core supply for the {signal.removeprefix('VCCK_').lower()} power domain."
        electrical = "Nominal 1.1 V supply."
    elif signal == "DDR2IO_V18":
        summary = "1.8 V DDR2 I/O supply."
        electrical = "Nominal 1.8 V supply."
    elif signal == "DDR2IO_VSS":
        summary = "DDR2 I/O ground."
        electrical = "Ground."
    elif signal == "DDR2_PLL_V33":
        summary = "3.3 V DDR2 PLL supply."
        electrical = "Nominal 3.3 V supply."
    elif signal in ("PGND", "PGND/DDR2IO_VSS"):
        summary = "Digital pad/DDR2 ground."
        electrical = "Ground."
    elif signal.startswith("AUDIO_HOUT"):
        summary = "Analogue headphone DAC output; alternate digital audio/GPIO."
    elif signal == "AUDIO_HP_GND":
        summary = "Analogue ground for the headphone output stage."
        electrical = "Analogue ground."
    elif signal == "AUDIO_HP_AVDD33":
        summary = "3.3 V analogue supply for the headphone output stage."
        electrical = "Nominal 3.3 V supply."
    elif signal.startswith("LINE_IN"):
        summary = "Analogue line input; alternate I2S/GPIO."
    elif signal.startswith("AUDIO_REF"):
        summary = "Audio analogue reference; alternate I2S clock/GPIO."
    elif signal.startswith("AUDIO_SOUT"):
        summary = "Analogue speaker DAC output; alternate digital audio/GPIO."
    elif signal == "AUDIO_DAC_GND":
        summary = "Analogue ground for the audio DAC."
        electrical = "Analogue ground."
    elif signal == "AUDIO_VDD33":
        summary = "3.3 V analogue supply for the audio DAC."
        electrical = "Nominal 3.3 V supply."
    elif signal.startswith("DPTX_LANE_"):
        summary = "Panel transmitter differential lane for eDP or V-by-One."
        electrical = "High-speed differential output; datasheet lists 3.3 V tolerance."
    elif signal == "DPTX_VDD11":
        summary = "1.1 V supply for the panel DisplayPort transmitter."
        electrical = "Nominal 1.1 V supply."
    elif signal == "DPTX_VDD33":
        summary = "3.3 V supply for the panel DisplayPort transmitter."
        electrical = "Nominal 3.3 V supply."
    elif signal.startswith("eDPTX_AUX"):
        summary = "Panel eDP AUX-channel pin, alternatively an MCU GPIO."
    elif signal.startswith("eDPTX_HPD"):
        summary = "Panel eDP hot-plug/lock input, alternatively an MCU GPIO."
    elif "USB_SPI" in signal:
        summary = "SPI control signal for an external USB device/hub; not USB D+/D−."
    elif signal.startswith("SPI_"):
        summary = "Dedicated external firmware-flash SPI signal."
        electrical = "Datasheet note: 3.3 V tolerance."
    elif signal.startswith("FLASH_WP"):
        summary = "External SPI-flash write-protect control, alternatively GPIO."
        electrical = "Datasheet note: 3.3 V tolerance."
    elif signal == "RESETB":
        summary = "Active-low scaler reset input."
        electrical = "Active low; datasheet identifies 5 V tolerance even while powered off."
    elif signal.startswith("DDCSCL"):
        summary = "HDMI/DVI DDC clock, alternatively an MCU GPIO."
    elif signal.startswith("DDCSDA"):
        summary = "HDMI/DVI DDC data, alternatively an MCU GPIO."
    elif signal.startswith("EEI2CSCL"):
        summary = "External EEPROM I2C clock, alternatively an MCU GPIO."
        electrical = "Datasheet note: 3.3 V tolerance."
    elif signal.startswith("EEI2CSDA"):
        summary = "External EEPROM I2C data, alternatively an MCU GPIO."
        electrical = "Datasheet note: 3.3 V tolerance."
    elif signal.startswith("EEWD"):
        summary = "External EEPROM write-disable control, alternatively an MCU GPIO."
        electrical = "Datasheet note: 3.3 V tolerance."
    elif "A-ADC" in signal:
        summary = "Five-bit low-speed ADC input for keys/sensors; alternate GPIO."
        electrical = "3.3 V tolerance as ADC; datasheet identifies 5 V tolerance when used as powered GPIO."
    elif "IR_RECEIVER" in signal:
        summary = "Infrared receiver input; alternate PWM/TCON/GPIO."
    elif "UART_TX" in signal:
        summary = "8051 UART transmit; alternate interrupt/GPIO/TCON."
    elif "UART_RX" in signal:
        summary = "8051 UART receive; alternate interrupt/GPIO/TCON."
    elif "PWM" in signal or "pwm_" in signal:
        summary = "PWM, timing-controller or MCU GPIO pad."
    elif "TCON" in signal or "GPIO" in signal:
        summary = "Timing-controller or MCU GPIO pad."
    else:
        summary = "Fixed or multiplexed scaler package signal."

    if "GPIO" in signal and electrical.startswith("See the"):
        electrical = "GPIO-capable pad; datasheet generally identifies 5 V tolerance when powered off."
    alternatives = [part.strip() for part in signal.split("/")]
    if len(alternatives) > 1:
        detail = f"Package pin {pin}. Available pin-share functions: {', '.join(alternatives)}. Only one function is active at a time."
    else:
        detail = f"Package pin {pin}. Datasheet signal: {signal}."
    return summary, detail, electrical


def enrich_record(record: dict[str, object]) -> dict[str, object]:
    pin = int(record["pin"])
    signal = str(record["datasheet_signal"])
    summary, description, electrical = pin_description(pin, signal)
    configured = str(record.get("configured_function") or "")
    demo_function = str(record.get("realtek_demo_function") or "")
    board_use = str(record.get("board_use") or "")
    if configured:
        description += f" Live pin-share decode: {configured}."
    if demo_function:
        description += f" Realtek QA-B reference profile selects: {demo_function}."
    if board_use and board_use not in ("board connection not traced", "mux pad; board load unresolved"):
        description += f" Reverse-engineered JXC board role: {board_use}."
    record.update({
        "mux": "Y" if record.get("gpio") else "N",
        "summary": summary,
        "description": description,
        "electrical_notes": electrical,
        "buses": ", ".join(bus_groups(signal)),
    })
    return record


def main() -> None:
    with LIVE.open(newline="") as f:
        live_rows = list(csv.DictReader(f, delimiter="\t"))
    mux = {}
    ports = [f"P1.{n}" for n in range(8)] + [f"P3.{n}" for n in range(8)]
    ports += [f"P4.{n}" for n in range(8)] + [f"P5.{n}" for n in range(8)]
    ports += [f"P6.{n}" for n in range(8)] + [f"P7.{n}" for n in range(8)]
    ports += [f"P8.{n}" for n in range(8)] + [f"P9.{n}" for n in range(8)]
    ports += [f"PA.{n}" for n in range(8)] + [f"PB.{n}" for n in range(5)]
    if len(live_rows) != 77 or len(ports) != 77:
        raise SystemExit(f"expected 77 mux pins, got rows={len(live_rows)} ports={len(ports)}")
    for row, port in zip(live_rows, ports):
        pin = int(row["pin"].split("_")[0])
        mux[pin] = (port, row)

    fields = ["pin", "datasheet_signal", "summary", "description", "electrical_notes", "buses", "mux", "gpio",
              "reference_signal", "pinshare_register", "live_raw", "configured_function", "realtek_demo_raw",
              "realtek_demo_function", "board_use", "confidence", "evidence", "coverage"]
    with OUT.open("w", newline="") as f:
        out = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        out.writeheader()
        for pin in range(1, 217):
            role, confidence, evidence = ROLE.get(pin, ("", "", ""))
            if pin in mux:
                port, row = mux[pin]
                out.writerow(enrich_record({
                    "pin": pin, "datasheet_signal": PACKAGE_SIGNAL[pin], "gpio": port,
                    "reference_signal": row["signal(ref board)"],
                    "pinshare_register": row["reg"], "live_raw": row["live"],
                    "configured_function": row["live_meaning"], "realtek_demo_raw": row["ref"],
                    "realtek_demo_function": row["ref_meaning"],
                    "board_use": role or "mux pad; board load unresolved",
                    "confidence": confidence or "unknown-load", "evidence": evidence or "live pin-share only",
                    "coverage": "firmware-visible mux pin",
                }))
            else:
                out.writerow(enrich_record({
                    "pin": pin, "datasheet_signal": PACKAGE_SIGNAL[pin],
                    "board_use": role or "board connection not traced",
                    "confidence": confidence or "package-function-only",
                    "evidence": evidence or f"RTD2795T-CG datasheet Table 1 ({DATASHEET})",
                    "coverage": "datasheet-identified fixed package pin",
                }))

    with OUT.open(newline="") as f:
        json_rows = list(csv.DictReader(f, delimiter="\t"))
    for row in json_rows:
        row["pin"] = int(row["pin"])
        row["buses"] = [item.strip() for item in row["buses"].split(",")]
    document = {
        "schema": "awto-ddc.rtd2795t-pin-ledger.v2",
        "device": "Realtek RTD2795T-CG",
        "package": "LQFP216",
        "realtek_demo_profile": "RL6449_QA_B_1A2MHL1DP1mDP_DPTX_eDP",
        "realtek_demo_profile_source": "tmp/sdcc-port/src/Pcb/RL6449/LQFP_216/RL6449_QA_B_1A2MHL1DP1mDP_DPTX_eDP_PINSHARE.h",
        "datasheet_source": {
            "url": DATASHEET,
            "title": "RTD2795T-CG Datasheet",
            "pin_table": "Table 1 - Signals Pin Assignment",
            "provenance": "third-party mirror; not an official Realtek host",
        },
        "local_evidence": [
            "docs/monitors/pinshare-live-AWT26110003.tsv",
            "docs/monitors/gpio-roles.md",
            "docs/reversing/dahua-fw/gpio-ir.md",
            "re/jxc-4k/gpio_audit.tsv",
            "fw/sdk/Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K_PINSHARE.h",
        ],
        "pins": json_rows,
    }
    with OUT_JSON.open("w") as f:
        json.dump(document, f, indent=2)
        f.write("\n")

    def md_cell(value: object) -> str:
        return str(value or "—").replace("|", "\\|").replace("\n", " ")

    md_lines = [
        "# RTD2795T-CG LQFP216 pin ledger",
        "",
        "Interactive filtered view: [open the HTML pin ledger](rtd2795t-216-pin-ledger.html).",
        "",
        "Interface-specific view: [open the bus explorer](rtd2795t-bus-view.html).",
        "",
        "Device capabilities and electrical data: [open the datasheet facts](rtd2795t-datasheet-facts.md).",
        "",
        "This is the human-readable view of the RE pin ledger. The JSON file is the canonical machine-readable form;",
        "the TSV is retained for spreadsheet and command-line processing.",
        "",
        f"Package-table source: [RTD2795T-CG Datasheet, Table 1]({DATASHEET}) (third-party mirror, not an official Realtek host).",
        "",
        "Board roles combine the package table with live pin-share state and original-firmware analysis. `—` means that",
        "the field does not apply or the PCB connection has not been traced.",
        "",
        "`Realtek QA-B demo use` is the SDK reference selection from `RL6449_QA_B_1A2MHL1DP1mDP_DPTX_eDP`;",
        "it is shown for comparison and is **not** the JXC board pinout. The SDK contains multiple other RL6449 layouts.",
        "",
    ]
    md_fields = [
        ("Pin", "pin"),
        ("Datasheet signal", "datasheet_signal"),
        ("One-line description", "summary"),
        ("Mux?", "mux"),
        ("Scaler GPIO", "gpio"),
        ("Live configured function", "configured_function"),
        ("Closest Realtek QA-B reference function", "realtek_demo_function"),
        ("JXC board use", "board_use"),
        ("Confidence", "confidence"),
    ]
    for first_pin in range(1, 217, 54):
        last_pin = first_pin + 53
        md_lines.extend([
            f"## Pins {first_pin}–{last_pin}",
            "",
            "| " + " | ".join(label for label, _ in md_fields) + " |",
            "| " + " | ".join("---" for _ in md_fields) + " |",
        ])
        for row in json_rows[first_pin - 1:last_pin]:
            md_lines.append("| " + " | ".join(md_cell(row[key]) for _, key in md_fields) + " |")
        md_lines.append("")
    OUT_MD.write_text("\n".join(md_lines))

    embedded_json = json.dumps(json_rows).replace("</", "<\\/")
    html = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RTD2795T-CG LQFP216 pin ledger</title>
<style>
  :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
  body { margin: 1.25rem; }
  h1 { margin-bottom: .35rem; }
  .source { color: #777; margin-top: 0; }
  .filters { position: sticky; top: 0; z-index: 2; display: flex; flex-wrap: wrap; gap: .8rem 1.2rem;
    align-items: center; padding: .8rem; border: 1px solid #8886; border-radius: .5rem; background: Canvas; }
  label { white-space: nowrap; }
  input[type=search] { min-width: 18rem; padding: .35rem .5rem; }
  #count { margin-left: auto; font-variant-numeric: tabular-nums; }
  .table-wrap { overflow: auto; }
  table { width: max-content; min-width: 100%; table-layout: auto; border-collapse: collapse; margin-top: 1rem; font-size: .9rem; }
  th, td { border: 1px solid #8886; padding: .35rem .5rem; text-align: left; vertical-align: top; }
  th { position: sticky; top: 4.1rem; height: 9.5rem; min-width: 1.7rem; padding: .4rem .25rem;
    background: Canvas; writing-mode: vertical-rl; transform: rotate(180deg); white-space: nowrap; }
  td { white-space: nowrap; }
  td:nth-child(3), td:nth-child(9) { white-space: normal; min-width: 18rem; max-width: 32rem; }
  td:first-child { text-align: right; font-variant-numeric: tabular-nums; }
  tr[data-status=confirmed] { background: color-mix(in srgb, #38b66b 17%, Canvas); }
  tr[data-status=inferred] { background: color-mix(in srgb, #f0ad2c 18%, Canvas); }
  tr[data-status=unused] { background: color-mix(in srgb, #348cff 22%, Canvas); }
  tr[data-status=unknown] { background: color-mix(in srgb, #e5484d 24%, Canvas); }
  tr[data-status=package] { background: color-mix(in srgb, #8b8b8b 12%, Canvas); }
  tr[data-kind=nc] { opacity: .65; }
  code { white-space: nowrap; }
</style>
</head>
<body>
<h1>RTD2795T-CG LQFP216 pin ledger</h1>
<p class="source">Package source: <a href="https://rtddisplay.com/upload/20231007170054.pdf">RTD2795T-CG Datasheet, Table 1</a> (third-party mirror).</p>
<p><strong>Reference warning:</strong> “Closest Realtek QA-B reference function” is one of 14 bundled vendor QA/demo layouts, not the JXC board pinout. It is displayed because it has the highest match (35/77 mux selections); the live and JXC columns are the board-specific evidence. <a href="rtd2795t-generic-board-match.md#sdk-profile-comparison">See the profile comparison.</a></p>
<p><a href="rtd2795t-bus-view.html">Open the interface/bus explorer</a> · <a href="rtd2795t-datasheet-facts.md">Read all extracted datasheet facts</a>. Hover over any row for all recorded detail.</p>
<div class="filters">
  <input id="search" type="search" placeholder="Filter pin, signal, function, board use…" aria-label="Search pins">
  <label><input id="show-power" type="checkbox"> Power / ground</label>
  <label><input id="show-fixed" type="checkbox"> Fixed function</label>
  <label><input id="show-mux" type="checkbox" checked> GPIO / mux</label>
  <label><input id="show-nc" type="checkbox"> NC</label>
  <span id="count"></span>
</div>
<p><small>GPIO notation: <code>P3D5</code> = port P3.5 · <code>i&lt;I&gt;</code> = input · <code>o&lt;PP&gt;</code> = push-pull output · <code>o&lt;OD&gt;</code> = open-drain output.<br>Status colours: <span style="background:#38b66b55">confirmed/configured</span> · <span style="background:#f0ad2c55">inferred</span> · <span style="background:#348cff55">unused</span> · <span style="background:#e5484d55">unknown load</span> · <span style="background:#8b8b8b44">package function only</span>.</small></p>
<div class="table-wrap"><table>
<thead><tr><th>Pin</th><th>Datasheet signal</th><th>One-line description</th><th>Interfaces</th><th>Mux?</th><th>Scaler GPIO</th><th>Live configured function</th><th>Closest Realtek QA-B reference function</th><th>JXC board use</th><th>Confidence</th></tr></thead>
<tbody id="pins"></tbody>
</table></div>
<script>
const rows = __PIN_ROWS__;
const powerPattern = /(?:^|[/_ ])(?:VDD|VSS|VCC|PVCC|PGND|GND|AVDD|33V|11V|18)(?:$|[/_ 0-9])/i;
function kind(row) {
  if (row.datasheet_signal === 'NC') return 'nc';
  if (powerPattern.test(row.datasheet_signal)) return 'power';
  if (row.gpio) return 'mux';
  return 'fixed';
}
function text(value) { return value || '—'; }
function explainMode(value) {
  return String(text(value))
    .replace(/P([0-9A-F])D(\d)i<I>/g, 'Port P$1.$2 input')
    .replace(/P([0-9A-F])D(\d)o<PP>/g, 'Port P$1.$2 push-pull output')
    .replace(/P([0-9A-F])D(\d)o<OD>/g, 'Port P$1.$2 open-drain output');
}
function status(row) {
  const use = row.board_use.toLowerCase(), confidence = row.confidence.toLowerCase();
  if (use.includes('unused')) return 'unused';
  if (confidence.includes('unknown') || confidence.includes('unresolved')) return 'unknown';
  if (confidence.startsWith('confirmed') || confidence === 'configured') return 'confirmed';
  if (confidence === 'inferred') return 'inferred';
  return 'package';
}
function esc(value) {
  return String(text(value)).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
function tooltip(row) {
  return [`Pin ${row.pin}: ${row.datasheet_signal}`, row.summary, row.description,
          `Electrical: ${row.electrical_notes}`, `Interfaces: ${row.buses.join(', ')}`,
          `GPIO: ${text(row.gpio)}`, `Live: ${text(row.configured_function)}`,
          `Realtek QA-B demo: ${text(row.realtek_demo_function)} (raw ${text(row.realtek_demo_raw)})`,
          `Board: ${text(row.board_use)}`, `Confidence: ${text(row.confidence)}`,
          `Evidence: ${text(row.evidence)}`].join('\n');
}
function render() {
  const query = document.querySelector('#search').value.trim().toLowerCase();
  const enabled = {
    power: document.querySelector('#show-power').checked,
    fixed: document.querySelector('#show-fixed').checked,
    mux: document.querySelector('#show-mux').checked,
    nc: document.querySelector('#show-nc').checked,
  };
  const visible = rows.filter(row => enabled[kind(row)] && (!query || Object.values(row).join(' ').toLowerCase().includes(query)));
  document.querySelector('#pins').innerHTML = visible.map(row => {
    const rowKind = kind(row);
    return `<tr data-kind="${rowKind}" data-status="${status(row)}" title="${esc(tooltip(row))}"><td>${row.pin}</td><td><code>${esc(row.datasheet_signal)}</code></td><td>${esc(row.summary)}</td><td>${esc(row.buses.join(', '))}</td><td>${row.mux}</td><td>${esc(row.gpio)}</td><td title="${esc(explainMode(row.configured_function))}">${esc(row.configured_function)}</td><td title="${esc(explainMode(row.realtek_demo_function))}">${esc(row.realtek_demo_function)}</td><td>${esc(row.board_use)}</td><td>${esc(row.confidence)}</td></tr>`;
  }).join('');
  document.querySelector('#count').textContent = `${visible.length} / ${rows.length} pins`;
}
document.querySelectorAll('input').forEach(input => input.addEventListener('input', render));
render();
</script>
</body>
</html>
'''.replace("__PIN_ROWS__", embedded_json)
    OUT_HTML.write_text(html)

    bus_html = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RTD2795T-CG interface and bus explorer</title>
<style>
  :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
  body { margin: 1.25rem; }
  .controls { position: sticky; top: 0; z-index: 2; display: flex; flex-wrap: wrap; gap: .8rem;
    align-items: center; padding: .8rem; border: 1px solid #8886; border-radius: .5rem; background: Canvas; }
  select, input { padding: .4rem .55rem; font: inherit; }
  input { min-width: 18rem; }
  #count { margin-left: auto; font-variant-numeric: tabular-nums; }
  .table-wrap { overflow: auto; }
  table { width: max-content; min-width: 100%; table-layout: auto; border-collapse: collapse; margin-top: 1rem; font-size: .9rem; }
  th, td { border: 1px solid #8886; padding: .4rem .55rem; text-align: left; vertical-align: top; }
  th { position: sticky; top: 4.2rem; height: 9.5rem; min-width: 1.7rem; padding: .4rem .25rem;
    background: Canvas; writing-mode: vertical-rl; transform: rotate(180deg); white-space: nowrap; }
  td:first-child { text-align: right; }
  code { white-space: nowrap; }
  .detail { min-width: 24rem; }
  tr[data-status=confirmed] { background: color-mix(in srgb, #38b66b 17%, Canvas); }
  tr[data-status=inferred] { background: color-mix(in srgb, #f0ad2c 18%, Canvas); }
  tr[data-status=unused] { background: color-mix(in srgb, #348cff 22%, Canvas); }
  tr[data-status=unknown] { background: color-mix(in srgb, #e5484d 24%, Canvas); }
  tr[data-status=package] { background: color-mix(in srgb, #8b8b8b 12%, Canvas); }
</style>
</head>
<body>
<h1>RTD2795T-CG interface and bus explorer</h1>
<p>Select one interface to see only its package pins. Multiplexed pins appear in every interface they support;
the “Live configured function” column shows what this JXC board currently selects.</p>
<p><strong>Reference warning:</strong> the QA-B column is the closest of 14 bundled vendor QA/demo layouts (35/77 mux selections), not the JXC board pinout.</p>
<p><small>GPIO notation: P3D5 = port P3.5 · i&lt;I&gt; = input · o&lt;PP&gt; = push-pull output · o&lt;OD&gt; = open-drain output.<br>Status colours: green confirmed/configured · amber inferred · blue unused · red unknown load · grey package function only.</small></p>
<p><a href="rtd2795t-216-pin-ledger.html">Return to the complete pin ledger</a> · <a href="rtd2795t-datasheet-facts.md">Read all extracted datasheet facts</a>.</p>
<div class="controls">
  <label for="bus">Interface:</label><select id="bus"></select>
  <input id="search" type="search" placeholder="Search within this interface…" aria-label="Search selected interface">
  <span id="count"></span>
</div>
<div class="table-wrap"><table>
<thead><tr><th>Pin</th><th>Datasheet signal</th><th>Mux?</th><th>Summary</th><th class="detail">Detailed description</th><th>Electrical notes</th><th>Live configured function</th><th>Closest Realtek QA-B reference function</th><th>JXC board use</th><th>Confidence</th></tr></thead>
<tbody id="pins"></tbody>
</table></div>
<script>
const rows = __PIN_ROWS__;
const busNames = [...new Set(rows.flatMap(row => row.buses))].sort((a, b) => a.localeCompare(b));
const busSelect = document.querySelector('#bus');
function countFor(name) { return rows.filter(row => row.buses.includes(name)).length; }
busSelect.innerHTML = busNames.map(name => `<option value="${name.replaceAll('"', '&quot;')}">${name} (${countFor(name)})</option>`).join('');
busSelect.value = 'HDMI / DVI';
function text(value) { return value || '—'; }
function explainMode(value) {
  return String(text(value))
    .replace(/P([0-9A-F])D(\d)i<I>/g, 'Port P$1.$2 input')
    .replace(/P([0-9A-F])D(\d)o<PP>/g, 'Port P$1.$2 push-pull output')
    .replace(/P([0-9A-F])D(\d)o<OD>/g, 'Port P$1.$2 open-drain output');
}
function status(row) {
  const use = row.board_use.toLowerCase(), confidence = row.confidence.toLowerCase();
  if (use.includes('unused')) return 'unused';
  if (confidence.includes('unknown') || confidence.includes('unresolved')) return 'unknown';
  if (confidence.startsWith('confirmed') || confidence === 'configured') return 'confirmed';
  if (confidence === 'inferred') return 'inferred';
  return 'package';
}
function esc(value) {
  return String(text(value)).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
function render() {
  const selected = busSelect.value;
  const query = document.querySelector('#search').value.trim().toLowerCase();
  const visible = rows.filter(row => row.buses.includes(selected) &&
    (!query || Object.values(row).flat().join(' ').toLowerCase().includes(query)));
  document.querySelector('#pins').innerHTML = visible.map(row =>
    `<tr data-status="${status(row)}"><td>${row.pin}</td><td><code>${esc(row.datasheet_signal)}</code></td><td>${row.mux}</td><td>${esc(row.summary)}</td><td>${esc(row.description)}</td><td>${esc(row.electrical_notes)}</td><td title="${esc(explainMode(row.configured_function))}">${esc(row.configured_function)}</td><td title="${esc(explainMode(row.realtek_demo_function))}">${esc(row.realtek_demo_function)}</td><td>${esc(row.board_use)}</td><td>${esc(row.confidence)}</td></tr>`
  ).join('');
  document.querySelector('#count').textContent = `${visible.length} pin${visible.length === 1 ? '' : 's'}`;
  location.hash = encodeURIComponent(selected);
}
const requested = decodeURIComponent(location.hash.slice(1));
if (busNames.includes(requested)) busSelect.value = requested;
busSelect.addEventListener('change', render);
document.querySelector('#search').addEventListener('input', render);
render();
</script>
</body>
</html>
'''.replace("__PIN_ROWS__", embedded_json)
    OUT_BUS_HTML.write_text(bus_html)
    print(
        f"wrote {OUT}, {OUT_JSON}, {OUT_MD}, {OUT_HTML}, and {OUT_BUS_HTML}: "
        f"216 named package pins, {len(mux)} firmware-visible mux pins"
    )


if __name__ == "__main__":
    main()
