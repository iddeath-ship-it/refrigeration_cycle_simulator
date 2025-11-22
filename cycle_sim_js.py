import streamlit as st
import matplotlib.pyplot as plt
import numpy as np
import CoolProp.CoolProp as CP
import json

class RefrigerationCycleWebSimulator:
    def __init__(self):
        if 'snapshots' not in st.session_state:
            st.session_state.snapshots = {}
        if 'current_cycle' not in st.session_state:
            st.session_state.current_cycle = None
        if 'current_freq' not in st.session_state:
            st.session_state.current_freq = 60.0
        if 'current_eev' not in st.session_state:
            st.session_state.current_eev = 50.0
        if 'current_fan' not in st.session_state:
            st.session_state.current_fan = 750
        self.snapshots = st.session_state.snapshots
        self.current_cycle = st.session_state.current_cycle
        self.current_freq = st.session_state.current_freq
        self.current_eev = st.session_state.current_eev
        self.current_fan = st.session_state.current_fan

    def setup_ui(self):
        st.title("에어컨 냉동사이클 시뮬레이터")

        # Input section
        st.header("제어요소 입력")
        col1, col2, col3 = st.columns(3)

        with col1:
            comp_freq = st.slider("압축기 주파수 (Hz)", min_value=30.0, max_value=120.0, value=60.0, step=0.1, key="comp_freq")
        with col2:
            eev_opening = st.slider("EEV 개도 (%)", min_value=0.0, max_value=100.0, value=50.0, step=0.1, key="eev_opening")
        with col3:
            fan_rpm = st.slider("실외팬 RPM", min_value=0, max_value=1500, value=750, step=10, key="fan_rpm")

        if st.button("계산 및 플롯"):
            self.calculate_cycle(comp_freq, eev_opening, fan_rpm)

    def calculate_cycle(self, freq, eev, fan):
        self.current_freq = freq
        self.current_eev = eev
        self.current_fan = fan

        # Simplified model
        # Base values for R32 at typical conditions
        refrigerant = 'R32'

        # Evaporation temperature based on EEV: base 5°C, increases with opening
        T_evap_base = 5  # °C
        T_evap = T_evap_base + (eev / 100) * 10  # Increase by 10°C at max opening

        # Condensation temperature based on fan RPM and compressor freq:
        # Base 50°C, decreases with fan RPM, increases with compressor freq (more heat load)
        T_cond_base = 50  # °C
        T_cond = T_cond_base - (fan / 1500) * 15 + (freq - 60) / 60 * 10  # Adjust for freq

        # Suction superheat: base 10°C, decreases with opening
        SH = 10 - (eev / 100) * 8  # Decrease by 8°C at max opening

        # Compression ratio and discharge temp increase with freq
        ratio_mult = freq / 60
        discharge_temp_raise = (freq - 60) * 0.1  # 0.1°C per Hz over 60

        P_evap = CP.PropsSI('P', 'T', T_evap + 273.15, 'Q', 1, refrigerant) / 1000  # kPa
        P_cond = CP.PropsSI('P', 'T', T_cond + 273.15, 'Q', 0, refrigerant) / 1000  # kPa

        T_suction = T_evap + SH
        h1 = CP.PropsSI('H', 'T', T_suction + 273.15, 'P', P_evap * 1000, refrigerant) / 1000  # kJ/kg

        # Isentropic compression
        s1 = CP.PropsSI('S', 'T', T_suction + 273.15, 'P', P_evap * 1000, refrigerant) / 1000  # kJ/kg/K
        P2 = P_cond * 1000
        T2s = CP.PropsSI('T', 'P', P2, 'S', s1 * 1000, refrigerant) - 273.15 + discharge_temp_raise
        h2s = CP.PropsSI('H', 'T', T2s + 273.15, 'P', P2, refrigerant) / 1000

        # Assume some efficiency, but for simplicity use isentropic
        h2 = h2s

        # Condenser outlet: saturated liquid
        T3 = T_cond
        h3 = CP.PropsSI('H', 'T', T3 + 273.15, 'Q', 0, refrigerant) / 1000

        # Expander: isenthalpic
        h4 = h3
        T4 = CP.PropsSI('T', 'H', h4 * 1000, 'P', P_evap * 1000, refrigerant) - 273.15

        points = {
            1: {"P": P_evap, "h": h1},
            2: {"P": P_cond, "h": h2},
            3: {"P": P_cond, "h": h3},
            4: {"P": P_evap, "h": h4}
        }

        self.current_cycle = points
        st.session_state.current_cycle = points
        st.session_state.current_freq = self.current_freq
        st.session_state.current_eev = self.current_eev
        st.session_state.current_fan = self.current_fan
        self.update_table(points)
        self.plot_cycle(points)

    def update_table(self, points):
        if points is None:
            return

        st.header("상태점 테이블 및 성능")

        import pandas as pd
        df = pd.DataFrame.from_dict(points, orient='index')
        df['상태점'] = df.index
        df = df[['상태점', 'P', 'h']].rename(columns={'P': '압력 (kPa)', 'h': '엔탈피 (kJ/kg)'})
        df = df.round(1)
        st.table(df.set_index('상태점'))

        # Calculate performance
        cooling_effect = points[1]['h'] - points[4]['h']
        compressor_work = points[2]['h'] - points[1]['h']
        eer = cooling_effect / compressor_work if compressor_work != 0 else 0

        col1, col2, col3 = st.columns(3)
        col1.metric("냉방효과", f"{cooling_effect:.1f} kJ/kg")
        col2.metric("압축기 일", f"{compressor_work:.1f} kJ/kg")
        col3.metric("EER", f"{eer:.2f}")

    def plot_cycle(self, points):
        if points is None:
            return

        st.header("P-H 선도")

        # Set font for Korean
        try:
            plt.rcParams['font.family'] = 'Malgun Gothic'
        except:
            try:
                plt.rcParams['font.family'] = ['DejaVu Sans', 'sans-serif']
            except:
                plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['axes.unicode_minus'] = False

        fig, ax = plt.subplots(figsize=(6, 5))

        # Get saturation curve
        refrigerant = 'R32'
        h_sat_liq = []
        h_sat_vap = []
        P_min = 200
        P_max = 3500
        P_range = np.linspace(P_min, P_max, 200)

        for P in P_range:
            h_l = CP.PropsSI('H', 'P', P * 1000, 'Q', 0, refrigerant) / 1000
            h_v = CP.PropsSI('H', 'P', P * 1000, 'Q', 1, refrigerant) / 1000
            h_sat_liq.append(h_l)
            h_sat_vap.append(h_v)

        ax.plot(h_sat_vap, P_range, 'b-', label='포화 증기', alpha=0.7)
        ax.plot(h_sat_liq, P_range, 'b-', label='포화 액체', alpha=0.7)

        # Plot cycle
        cycle_h = [points[1]['h'], points[2]['h'], points[3]['h'], points[4]['h'], points[1]['h']]
        cycle_p = [points[1]['P'], points[2]['P'], points[3]['P'], points[4]['P'], points[1]['P']]

        ax.plot(cycle_h, cycle_p, 'r-o', label='냉동사이클', linewidth=2)

        # Annotate points
        for i in range(1, 5):
            h, p = points[i]['h'], points[i]['P']
            ax.annotate(f'{i}', (h, p), xytext=(5, 5), textcoords='offset points', fontsize=10, fontweight='bold')

        ax.set_xlabel('엔탈피 (kJ/kg)')
        ax.set_ylabel('압력 (kPa)')
        ax.set_title('냉매 R32 냉동사이클 P-H 선도')
        ax.legend()
        ax.grid(True)
        ax.set_xlim(min(h_sat_liq) - 50, 800)
        ax.set_ylim(P_min, P_max)
        st.pyplot(fig)

    def setup_snapshots(self):
        st.sidebar.header("스냅샷 관리")

        if st.sidebar.button("저장"):
            if self.current_cycle:
                name = f"압축_{self.current_freq:.1f}Hz_EEV_{self.current_eev:.1f}%_팬_{int(self.current_fan)}RPM"
                if name in self.snapshots:
                    st.sidebar.warning("이 설정의 스냅샷이 이미 존재합니다.")
                else:
                    self.snapshots[name] = {
                        "cycle": self.current_cycle,
                        "settings": {
                            "freq": self.current_freq,
                            "eev": self.current_eev,
                            "fan": self.current_fan
                        }
                    }
                    st.session_state.snapshots = self.snapshots
                    st.sidebar.success(f"스냅샷 '{name}' 저장됨")
            else:
                st.sidebar.error("계산을 먼저 수행하세요")

        snap_names = list(self.snapshots.keys())
        if snap_names:
            selected = st.sidebar.selectbox("스냅샷 선택", snap_names)

            if st.sidebar.button("불러오기", key="load_button"):
                data = self.snapshots[selected]
                st.session_state["comp_freq"] = data["settings"]["freq"]
                st.session_state["eev_opening"] = data["settings"]["eev"]
                st.session_state["fan_rpm"] = data["settings"]["fan"]
                self.current_cycle = data["cycle"]
                self.current_freq = data["settings"]["freq"]
                self.current_eev = data["settings"]["eev"]
                self.current_fan = data["settings"]["fan"]
                st.session_state.current_cycle = self.current_cycle
                st.session_state.current_freq = self.current_freq
                st.session_state.current_eev = self.current_eev
                st.session_state.current_fan = self.current_fan
                self.update_table(self.current_cycle)
                self.plot_cycle(self.current_cycle)
                st.sidebar.success("스냅샷 불러옴")

            if st.sidebar.button("삭제"):
                del self.snapshots[selected]
                st.session_state.snapshots = self.snapshots
                st.sidebar.success("스냅샷 삭제됨")
        else:
            st.sidebar.write("저장된 스냅샷이 없습니다")

def main():
    app = RefrigerationCycleWebSimulator()
    app.setup_snapshots()
    app.setup_ui()

if __name__ == "__main__":
    main()
