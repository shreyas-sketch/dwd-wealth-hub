// /terms, /privacy, /disclosures — short placeholder legal pages (to be replaced by counsel-reviewed text).
import brand from "@/brand";
import PublicLayout from "../components/PublicLayout";
import { Card, PageHeader } from "../components/ui";

function LegalPage({ eyebrow, title, accent, children }) {
  return (
    <PublicLayout>
      <div className="px-4 md:px-8 py-8 sm:py-12 max-w-[760px] mx-auto">
        <PageHeader eyebrow={["Legal", `_${eyebrow}`]} title={title} accent={accent} />
        <Card inset className="mb-6"><p className="text-[14px]">Placeholder text. The final version will be published before launch.</p></Card>
        <div className="space-y-5 text-[16px] leading-relaxed [&_h2]:font-bzserif [&_h2]:text-[22px] [&_h2]:font-semibold [&_h2]:mt-8 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-1.5">
          {children}
        </div>
      </div>
    </PublicLayout>
  );
}

const RISK = (
  <>
    <h2>Crypto is high risk</h2>
    <ul>
      <li>Crypto assets are <b>unregulated in India</b>. There is no regulator or investor-protection scheme to go to if something goes wrong.</li>
      <li>Prices can rise or fall very sharply, even in one day. You can lose most or all of the money you put in.</li>
      <li>Only put in money you can afford to lose. Do not borrow to buy crypto.</li>
    </ul>
    <h2>Tax</h2>
    <ul>
      <li>Gains from crypto (virtual digital assets) are taxed at a flat <b>30%</b> plus cess. Losses cannot be set off against other income.</li>
      <li><b>1% TDS</b> is deducted when you sell or transfer crypto above the limits set by law.</li>
      <li>Speak to a tax professional for your own situation.</li>
    </ul>
    <h2>Not investment advice</h2>
    <p>{brand.name} is an education and research tool. Verdicts, forecasts, X-Ray results, plans, baskets and answers from the AI coach are general information produced by software. They are not a recommendation to buy, sell or hold any asset, and they are not personal financial advice. Past prices and past results do not promise future returns.</p>
  </>
);

export function Terms() {
  return (
    <LegalPage eyebrow="Terms" title="Terms of" accent="use.">
      <p>By using {brand.name} you agree to these terms.</p>
      <h2>The service</h2>
      <p>{brand.name} gives you tools to learn about crypto: coin checks, daily verdicts, forecasts, a goal planner with practice money, and, if you link your own exchange, automatic buys from your own account. We never hold your money or your coins.</p>
      <h2>Your account</h2>
      <p>One account per mobile number. Keep your phone safe; anyone with access to your codes can open your account.</p>
      <h2>Plans and payments</h2>
      <p>Paid plans are monthly subscriptions through Razorpay and renew automatically until you cancel. Cancelling stops the next renewal; your plan runs to the end of the paid month.</p>
      <h2>Exchange links</h2>
      <p>When you link an exchange you give us a trade-only API key. We refuse keys that can withdraw. You are responsible for the orders placed from your plans.</p>
      {RISK}
    </LegalPage>
  );
}

export function Privacy() {
  return (
    <LegalPage eyebrow="Privacy" title="Privacy" accent="policy.">
      <h2>What we collect</h2>
      <ul>
        <li>Your mobile number (to log you in) and, if you add them, your name and email.</li>
        <li>What you check and use in the app, so we can show your history and limits.</li>
        <li>If you link an exchange: your API key, stored encrypted, and your balances and orders.</li>
        <li>Where you came from (for example a webinar link), to understand which events help people.</li>
      </ul>
      <h2>What we don't do</h2>
      <ul>
        <li>We don't sell your data.</li>
        <li>We don't ask for keys that can withdraw from your exchange.</li>
      </ul>
      <h2>Your choices</h2>
      <p>You can update your name and email in Account, and ask us to delete your account at any time.</p>
    </LegalPage>
  );
}

export function Disclosures() {
  return (
    <LegalPage eyebrow="Disclosures" title="Risk" accent="disclosures.">
      {RISK}
      <h2>About AI answers</h2>
      <p>Many screens are written by AI models from market data and our teaching material. AI can be wrong or out of date. Always check before you act.</p>
    </LegalPage>
  );
}
