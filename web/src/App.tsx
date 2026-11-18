import { Route, Routes } from "react-router-dom";
import { Gallery } from "./routes/Gallery";
import { Operator } from "./routes/Operator";
import { Program } from "./routes/Program";
import { Setup } from "./routes/Setup";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Operator />} />
      <Route path="/setup" element={<Setup />} />
      <Route path="/program" element={<Program />} />
      <Route path="/gallery" element={<Gallery />} />
      <Route path="*" element={<Operator />} />
    </Routes>
  );
}
