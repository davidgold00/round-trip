# Interview notes

Five talking points. Each is written to be said out loud in about ninety
seconds.

---

## 1. The question

Everyone has noticed that Nvidia invests in OpenAI, and that OpenAI buys from
Nvidia. The interesting question is not whether that happens. It is how much of
the industry's disclosed backlog actually sits on it.

So I made the question narrow enough to answer: for each seller of AI
infrastructure, what share of its own disclosed backlog is owed by a customer
whose funding traces back to that same seller? Not "is this a bubble". Not "is
the backlog real". One thing: how much of the promise to pay was financed by the
party being paid.

Narrow enough that the answer can be checked line by line, and every line has a
filing behind it.

---

## 2. The metric design, and why bounds

Two matrices. **D** is the share of a seller's disclosed backlog that a named
customer has committed. **Provenance** is how much of that customer's funding
came from the seller. Multiply and sum.

The hard part is the provenance denominator, because it is unknowable. OpenAI,
Anthropic and xAI file nothing. Their total external funding is only ever a
documented subset. So I report three readings instead of one number:

* **LOWER**: dollars the seller demonstrably handed the buyer, over what the
  buyer promised to pay the seller. Direct edges only.
* **CENTRAL**: the seller's share of the buyer's whole documented funding, with
  funding that arrives through intermediaries traced back and discounted.
* **UPPER**: if the seller funded the buyer at all, the whole commitment counts.

Here is why that mattered concretely. Early on, Anthropic's only recorded
funders were Amazon, Microsoft, Nvidia and AMD, because those are the companies
that disclose. The denominator was made entirely of suppliers, so every
supplier's share was inflated by construction. Once I added Anthropic's Series G
and Series H, where most of the money came from Altimeter, Sequoia, GIC, Coatue
and so on, the ecosystem figure fell from 3.1% to 1.7%. **Nearly half the
headline was an artefact of who files.**

A single point estimate would have hidden that. The bounds made it visible.

---

## 3. The headline finding

**Roughly 1.7%, range 1.4% to 18.2%**, of disclosed backlog depends on a
counterparty whose funding traces back to the seller. About $47 billion against
$2.7 trillion of disclosed backlog.

That is a smaller number than the narrative implies, and the reason is the real
finding: **79% of that backlog universe names no customer at all.**

Oracle discloses $664 billion of remaining performance obligations. The word
OpenAI appears nowhere in its filings. Broadcom discloses $179 billion including
a custom AI accelerator contract, with no customer and no split. CoreWeave's
largest customer was 67% of its 2025 revenue and is called "Customer A".

So the honest statement is not "round-trip exposure is low". It is: **of the
fifth of this backlog that anyone can attribute, round-trip financing explains a
small part, and the other four fifths cannot be checked by anyone outside those
companies.** That is a disclosure finding, and it is more useful than the
percentage.

There is a mirror of this on the supply side. Nvidia and AMD, the two companies
most associated with vendor financing, sell on purchase orders and disclose no
product backlog. There is no denominator for them, so they carry no headline
number here at all. The companies most discussed are the least measurable.

---

## 4. The surprising structural result

Two things surfaced that I did not go looking for.

**The strongly connected component.** Five nodes form one mutual-dependency
cluster: AMD, Amazon, Anthropic, Microsoft and OpenAI. Every one can reach every
other through funding or commitments, so none can be analysed in isolation.
Nine circular loops, all of them genuine round trips, the widest with a $24
billion bottleneck between Amazon and OpenAI.

**The second one was better.** The news monitor surfaced an S-1 from a neocloud
called Nscale, filed in September 2026. In one document: Nvidia holds warrants
over its Series B shares, Nvidia guarantees $860 million of its Texas data
centre lease, Nvidia is buying $1 billion of its convertible notes, and Nvidia
has separately committed to buy $1.2 billion of GPU capacity from it. Meanwhile
Microsoft has signed statements of work worth up to $43.8 billion and Anthropic
up to $44.6 billion.

Nvidia is simultaneously that company's supplier, its shareholder, its lease
guarantor, its lender and its customer.

The twist: **Nscale is the only filer in the dataset that names its
counterparties with dollar amounts.** Not because it is unusual, but because it
is doing an IPO, so its risk factors have to be specific. Every incumbent with
the same structures discloses them in aggregate. The clearest picture in the
whole dataset came from the smallest company in it, purely because it is
raising money.

---

## 5. The main limitation

**The answer is assumption-dominated on the stress side, and disclosure-limited
on the measurement side.**

On stress: the widest parameter swing is bigger than half the base result.
Pass-through, which is how much of a funding shortfall converts into less
buying rather than being absorbed by cash on hand, is worth 5.9 percentage
points on its own against a base of 5.8%. The Monte Carlo band is 3.4% to 8.5%.
That band is mostly me, not the data. The dashboard says so in those words.

On measurement: I am reporting on the fifth of the backlog that has a name on
it. I ran a second method, Eisenberg-Noe clearing, as a cross-check, and its
unshocked baseline is 11.4%. Meaning: before any shock, committed purchases in
this network already exceed documented external funding. That is either a real
signal about forward commitments running ahead of funding, or it is an artefact
of how little of that funding is documented. I cannot currently distinguish
those two, and I say that rather than picking the more interesting one.

What would change my mind, in order: Oracle or Broadcom naming a customer and a
split, which is $843 billion of currently unattributed backlog and would move
the answer more than any parameter in the model; an OpenAI or Anthropic S-1 with
a real funding table; and the Nvidia and OpenAI letter of intent converting to a
signed, sized investment, since it is the largest single row in the ledger and
it is still non-binding.
