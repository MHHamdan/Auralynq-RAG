import { Nav } from "@/components/landing/Nav";
import { Hero } from "@/components/landing/Hero";
import { Features } from "@/components/landing/Features";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { Stack } from "@/components/landing/Stack";
import { CTA } from "@/components/landing/CTA";
import { Footer } from "@/components/landing/Footer";

export default function Landing() {
  return (
    <div className="min-h-screen">
      <Nav />
      <main>
        <Hero />
        <Features />
        <HowItWorks />
        <Stack />
        <CTA />
      </main>
      <Footer />
    </div>
  );
}
