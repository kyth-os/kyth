import { HubPage } from "./HubPage";
import { THIS_PC_SECTIONS } from "../data/hubSections";
import { GuardianSection } from "../components/GuardianSection";
import { HardwareSection } from "../components/HardwareSection";
import { KernelSection } from "../components/KernelSection";
import { NvidiaSection } from "../components/NvidiaSection";
import { RepairSection } from "../components/RepairSection";
import { ChannelsSection } from "../components/ChannelsSection";
import { PlasmaWaylandSection } from "../components/PlasmaWaylandSection";
import { DiagnosticsSection } from "../components/DiagnosticsSection";
import { JustSection } from "../components/JustSection";
import { FeedbackSection } from "../components/FeedbackSection";
import { ThisPcOverview } from "../components/ThisPcOverview";

export function ThisPc() {
  return (
    <div className="this-pc-page">
      <ThisPcOverview />
      <div className="this-pc-controls-heading">
        <div>
          <span className="this-pc-eyebrow">System controls</span>
          <h2>Detailed tools</h2>
          <p>Open a focused control only when you need to change or investigate something.</p>
        </div>
      </div>
      <HubPage
        sections={THIS_PC_SECTIONS}
        sectionContent={{
          Guardian: GuardianSection,
          Hardware: HardwareSection,
          Kernel: KernelSection,
          NVIDIA: NvidiaSection,
          Repair: RepairSection,
          Channels: ChannelsSection,
          "Plasma Wayland": PlasmaWaylandSection,
          Diagnostics: DiagnosticsSection,
          Just: JustSection,
          Feedback: FeedbackSection,
        }}
      />
    </div>
  );
}
