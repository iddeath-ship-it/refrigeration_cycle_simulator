import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.font_manager import FontProperties
import json
import os
import numpy as np
import CoolProp.CoolProp as CP

class RefrigerationCycleSimulator:
    def __init__(self, root):
        self.root = root
        self.root.title("에어컨 냉동사이클 시뮬레이터")
        self.snapshots = {}
        self.current_cycle = None
        self.setup_ui()

    def setup_ui(self):
        # Input frame
        input_frame = ttk.LabelFrame(self.root, text="제어요소 입력")
        input_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        ttk.Label(input_frame, text="압축기 주파수 (Hz):").grid(row=0, column=0, sticky="w")
        self.comp_freq = ttk.Scale(input_frame, from_=30, to=120, orient=tk.HORIZONTAL,
                                   command=lambda v: self.freq_label.config(text=f"{float(v):.1f} Hz"))
        self.comp_freq.set(60)
        self.comp_freq.grid(row=0, column=1, sticky="ew")
        self.freq_label = ttk.Label(input_frame, text="60.0 Hz")
        self.freq_label.grid(row=0, column=2)

        ttk.Label(input_frame, text="EEV 개도 (%):").grid(row=1, column=0, sticky="w")
        self.eev_opening = ttk.Scale(input_frame, from_=0, to=100, orient=tk.HORIZONTAL,
                                     command=lambda v: self.eev_label.config(text=f"{float(v):.1f} %"))
        self.eev_opening.set(50)
        self.eev_opening.grid(row=1, column=1, sticky="ew")
        self.eev_label = ttk.Label(input_frame, text="50.0 %")
        self.eev_label.grid(row=1, column=2)

        ttk.Label(input_frame, text="실외팬 RPM:").grid(row=2, column=0, sticky="w")
        self.fan_rpm = ttk.Scale(input_frame, from_=0, to=1500, orient=tk.HORIZONTAL,
                                 command=lambda v: self.fan_label.config(text=f"{int(float(v))} RPM"))
        self.fan_rpm.set(750)
        self.fan_rpm.grid(row=2, column=1, sticky="ew")
        self.fan_label = ttk.Label(input_frame, text="750 RPM")
        self.fan_label.grid(row=2, column=2)

        ttk.Button(input_frame, text="계산 및 플롯", command=self.calculate_cycle).grid(row=3, columnspan=3, pady=10)

        # Table frame
        table_frame = ttk.LabelFrame(self.root, text="상태점 테이블 및 성능")
        table_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")

        self.tree = ttk.Treeview(table_frame, columns=("point", "P (kPa)", "h (kJ/kg)"), show="headings")
        self.tree.heading("point", text="상태점")
        self.tree.heading("P (kPa)", text="압력 (kPa)")
        self.tree.heading("h (kJ/kg)", text="엔탈피 (kJ/kg)")
        self.tree.pack(fill="both", expand=True)

        # Performance labels
        perf_frame = ttk.Frame(table_frame)
        perf_frame.pack(fill="x", pady=5)
        self.cool_eff_label = ttk.Label(perf_frame, text="냉방효과: -- kJ/kg")
        self.cool_eff_label.pack(side="left", padx=10)
        self.work_label = ttk.Label(perf_frame, text="압축기 일: -- kJ/kg")
        self.work_label.pack(side="left", padx=10)
        self.eer_label = ttk.Label(perf_frame, text="EER: --")
        self.eer_label.pack(side="left", padx=10)

        # Plot frame
        plot_frame = ttk.LabelFrame(self.root, text="P-H 선도")
        plot_frame.grid(row=0, column=1, rowspan=2, padx=10, pady=10, sticky="nsew")

        self.fig = plt.Figure(figsize=(6, 5))
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # Snapshot frame
        snap_frame = ttk.LabelFrame(self.root, text="스냅샷 관리")
        snap_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

        ttk.Button(snap_frame, text="스냅샷 저장", command=self.save_snapshot).grid(row=0, column=0, padx=5)
        ttk.Button(snap_frame, text="스냅샷 불러오기", command=self.load_snapshot).grid(row=0, column=1, padx=5)
        ttk.Button(snap_frame, text="스냅샷 삭제", command=self.delete_snapshot).grid(row=0, column=2, padx=5)

        self.snap_list = tk.Listbox(snap_frame, height=5)
        self.snap_list.grid(row=1, column=0, columnspan=3, sticky="ew", padx=5, pady=5)
        self.snap_list.bind("<<ListboxSelect>>", self.on_snapshot_select)

        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

    def calculate_cycle(self):
        freq = self.comp_freq.get()
        eev = self.eev_opening.get()
        fan = self.fan_rpm.get()

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
        self.update_table(points)
        self.plot_cycle(points)

    def update_table(self, points):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for point, props in points.items():
            self.tree.insert("", "end", values=(point, f"{props['P']:.1f}", f"{props['h']:.1f}"))

        # Calculate performance
        cooling_effect = points[1]['h'] - points[4]['h']
        compressor_work = points[2]['h'] - points[1]['h']
        eer = cooling_effect / compressor_work if compressor_work != 0 else 0

        self.cool_eff_label.config(text=f"냉방효과: {cooling_effect:.1f} kJ/kg")
        self.work_label.config(text=f"압축기 일: {compressor_work:.1f} kJ/kg")
        self.eer_label.config(text=f"EER: {eer:.2f}")

    def plot_cycle(self, points):
        self.ax.clear()

        # Set font for Korean - try different approaches
        try:
            plt.rcParams['font.family'] = 'Malgun Gothic'  # Windows Korean font
        except:
            try:
                plt.rcParams['font.family'] = ['DejaVu Sans', 'NanumGothic', 'sans-serif']
            except:
                plt.rcParams['font.family'] = 'sans-serif'

        # Ensure UTF-8 encoding for Korean text
        plt.rcParams['axes.unicode_minus'] = False

        # Get saturation curve (fixed range)
        refrigerant = 'R32'
        T_crit = CP.PropsSI('Tcrit', refrigerant) - 273.15
        h_sat_liq = []
        h_sat_vap = []
        P_min = 200  # kPa, fixed low pressure
        P_max = 3500  # kPa, fixed high pressure (increased)
        P_range = np.linspace(P_min, P_max, 200)

        for P in P_range:
            h_l = CP.PropsSI('H', 'P', P * 1000, 'Q', 0, refrigerant) / 1000
            h_v = CP.PropsSI('H', 'P', P * 1000, 'Q', 1, refrigerant) / 1000
            h_sat_liq.append(h_l)
            h_sat_vap.append(h_v)

        self.ax.plot(h_sat_vap, P_range, 'b-', label='포화 증기', alpha=0.7)
        self.ax.plot(h_sat_liq, P_range, 'b-', label='포화 액체', alpha=0.7)

        # Plot cycle (closed loop)
        cycle_h = [points[1]['h'], points[2]['h'], points[3]['h'], points[4]['h'], points[1]['h']]
        cycle_p = [points[1]['P'], points[2]['P'], points[3]['P'], points[4]['P'], points[1]['P']]

        self.ax.plot(cycle_h, cycle_p, 'r-o', label='냉동사이클', linewidth=2)

        # Annotate points
        for i in range(1, 5):
            h, p = points[i]['h'], points[i]['P']
            self.ax.annotate(f'{i}', (h, p), xytext=(5, 5), textcoords='offset points', fontsize=10, fontweight='bold')

        self.ax.set_xlabel('엔탈피 (kJ/kg)')
        self.ax.set_ylabel('압력 (kPa)')
        self.ax.set_title('냉매 R32 냉동사이클 P-H 선도')
        self.ax.legend()
        self.ax.grid(True)
        # Set fixed axis limits (increased upper limits)
        self.ax.set_xlim(min(h_sat_liq) - 50, 800)  # h up to 800
        self.ax.set_ylim(P_min, P_max)  # P up to 3500
        self.canvas.draw()

    def save_snapshot(self):
        if not self.current_cycle:
            messagebox.showerror("오류", "먼저 계산을 수행하세요.")
            return

        freq = self.comp_freq.get()
        eev = self.eev_opening.get()
        fan = self.fan_rpm.get()
        name = f"압축_{freq:.1f}Hz_EEV_{eev:.1f}%_팬_{int(fan)}RPM"

        if name in self.snapshots:
            messagebox.showinfo("알림", "이 설정의 스냅샷이 이미 존재합니다.")
            return

        self.snapshots[name] = {
            "comp_freq": freq,
            "eev_opening": eev,
            "fan_rpm": fan,
            "cycle": self.current_cycle
        }
        self.update_snap_list()

    def load_snapshot(self):
        sel = self.snap_list.curselection()
        if not sel:
            messagebox.showerror("오류", "스냅샷을 선택하세요.")
            return

        name = self.snap_list.get(sel[0])
        if name in self.snapshots:
            data = self.snapshots[name]
            self.comp_freq.set(data["comp_freq"])
            self.eev_opening.set(data["eev_opening"])
            self.fan_rpm.set(data["fan_rpm"])
            self.freq_label.config(text=f"{data['comp_freq']:.1f} Hz")
            self.eev_label.config(text=f"{data['eev_opening']:.1f} %")
            self.fan_label.config(text=f"{int(data['fan_rpm'])} RPM")
            self.current_cycle = data["cycle"]
            self.update_table(self.current_cycle)
            self.plot_cycle(self.current_cycle)

    def delete_snapshot(self):
        sel = self.snap_list.curselection()
        if not sel:
            messagebox.showerror("오류", "삭제할 스냅샷을 선택하세요.")
            return

        name = self.snap_list.get(sel[0])
        if name in self.snapshots:
            del self.snapshots[name]
            self.update_snap_list()

    def update_snap_list(self):
        self.snap_list.delete(0, tk.END)
        for name in self.snapshots:
            self.snap_list.insert(tk.END, name)

    def on_snapshot_select(self, event):
        # Can be used to preview or something, but not needed
        pass

if __name__ == "__main__":
    root = tk.Tk()
    app = RefrigerationCycleSimulator(root)
    root.mainloop()
