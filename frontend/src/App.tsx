import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { DashboardLayout } from "@/components/DashboardLayout";
import { Ambiguities } from "@/pages/Ambiguities";
import { CleanRequirements, MissingInformation } from "@/pages/CleanRequirements";
import { Dependencies } from "@/pages/Dependencies";
import { Landing } from "@/pages/Landing";
import { Overview } from "@/pages/Overview";
import { Contradictions, Duplicates } from "@/pages/PairReports";
import { Traceability } from "@/pages/Traceability";
import { Upload } from "@/pages/Upload";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/dashboard/:documentId" element={<DashboardLayout />}>
          <Route index element={<Overview />} />
          <Route path="requirements" element={<CleanRequirements />} />
          <Route path="ambiguities" element={<Ambiguities />} />
          <Route path="contradictions" element={<Contradictions />} />
          <Route path="duplicates" element={<Duplicates />} />
          <Route path="missing-information" element={<MissingInformation />} />
          <Route path="dependencies" element={<Dependencies />} />
          <Route path="traceability" element={<Traceability />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
