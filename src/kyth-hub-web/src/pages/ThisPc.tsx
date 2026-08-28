import { HubPage } from "./HubPage";
import { THIS_PC_SECTIONS } from "../data/hubSections";
import { UpdatesSection } from "../components/UpdatesSection";
import { GuardianSection } from "../components/GuardianSection";
import { HardwareSection } from "../components/HardwareSection";
import { KernelSection } from "../components/KernelSection";
import { NvidiaSection } from "../components/NvidiaSection";
import { RepairSection } from "../components/RepairSection";

export function ThisPc() {
  return (
    <HubPage
      sections={THIS_PC_SECTIONS}
      customContent={{
        Update: UpdatesSection,
        Guardian: GuardianSection,
        Hardware: HardwareSection,
        Kernel: KernelSection,
        NVIDIA: NvidiaSection,
        Repair: RepairSection,
      }}
    />
  );
}
