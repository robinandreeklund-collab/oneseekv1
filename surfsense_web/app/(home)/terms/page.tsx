import type { Metadata } from "next";

export const metadata: Metadata = {
	title: "Användarvillkor | Oneseek",
	description: "Användarvillkor för Oneseek-applikationen",
};

export default function TermsOfService() {
	return (
		<div className="container max-w-4xl mx-auto py-12 px-4">
			<h1 className="text-4xl font-bold mb-8">Användarvillkor</h1>

			<div className="prose dark:prose-invert max-w-none">
				<p className="text-lg mb-6">Senast uppdaterad: {new Date().toLocaleDateString()}</p>

				<section className="mb-8">
					<h2 className="text-2xl font-semibold mb-4">1. Inledning</h2>
					<p>
						Välkommen till Oneseek. Dessa användarvillkor reglerar din åtkomst till och användning
						av Oneseeks webbplats och tjänster. Genom att använda våra tjänster godkänner du att
						vara bunden av dessa villkor.
					</p>
					<p className="mt-4">
						Vänligen läs dessa villkor noggrant innan du använder våra tjänster. Genom att använda
						våra tjänster godkänner du att dessa villkor styr din relation med oss. Om du inte
						godkänner dessa villkor, vänligen avstå från att använda våra tjänster.
					</p>
				</section>

				<section className="mb-8">
					<h2 className="text-2xl font-semibold mb-4">2. Användning av våra tjänster</h2>
					<p>
						Du måste följa de policyer som görs tillgängliga för dig inom tjänsterna. Du får endast
						använda våra tjänster i enlighet med lag. Vi kan tillfälligt eller permanent upphöra att
						tillhandahålla våra tjänster till dig om du inte följer våra villkor eller policyer,
						eller om vi utreder misstänkt missbruk.
					</p>
					<p className="mt-4">
						Användning av våra tjänster ger dig ingen äganderätt till immateriella rättigheter i
						våra tjänster eller det innehåll du får tillgång till. Du får inte använda innehåll från
						våra tjänster utan tillstånd från rättighetsinnehavaren eller om det annars är tillåtet
						enligt lag.
					</p>
					<p className="mt-4">
						Vi förbehåller oss rätten att ta bort innehåll som vi skäligen anser bryter mot dessa
						villkor, gör intrång i immateriella rättigheter, är kränkande, olagligt eller på annat
						sätt olämpligt.
					</p>
				</section>

				<section className="mb-8">
					<h2 className="text-2xl font-semibold mb-4">3. Ditt konto</h2>
					<p>
						För att använda vissa av våra tjänster kan du behöva skapa ett konto. Du ansvarar för
						att skydda lösenordet som används för att få åtkomst till tjänsterna och för alla
						aktiviteter som sker under ditt lösenord.
					</p>
					<p className="mt-4">
						Du måste lämna korrekta och fullständiga uppgifter när du skapar ditt konto. Du samtycker
						till att uppdatera dina uppgifter för att hålla dem korrekta och fullständiga. Du ansvarar
						för att upprätthålla sekretessen för ditt konto och lösenord, inklusive att begränsa
						åtkomst till din dator och/eller ditt konto.
					</p>
					<p className="mt-4">
						Vi förbehåller oss rätten att vägra tjänst, avsluta konton, ta bort eller redigera
						innehåll eller avbryta beställningar efter eget gottfinnande.
					</p>
				</section>

				<section className="mb-8">
					<h2 className="text-2xl font-semibold mb-4">4. Integritet och upphovsrätt</h2>
					<p>
						Våra integritetspolicyer förklarar hur vi behandlar dina personuppgifter och skyddar din
						integritet när du använder våra tjänster. Genom att använda våra tjänster samtycker du
						till att Oneseek får använda sådana uppgifter i enlighet med våra integritetspolicyer.
					</p>
					<p className="mt-4">
						Vi svarar på meddelanden om påstådda upphovsrättsintrång och avslutar konton för
						återkommande intrång i enlighet med tillämplig upphovsrättslagstiftning.
					</p>
				</section>

				<section className="mb-8">
					<h2 className="text-2xl font-semibold mb-4">5. Licens och immateriella rättigheter</h2>
					<p>
						Oneseek ger dig en personlig, världsomspännande, royaltyfri, icke-överlåtbar och
						icke-exklusiv licens att använda den programvara som tillhandahålls som en del av
						tjänsterna. Denna licens har som enda syfte att du ska kunna använda och dra nytta av
						tjänsterna som tillhandahålls av Oneseek, på det sätt som tillåts enligt dessa villkor.
					</p>
					<p className="mt-4">
						Allt innehåll som ingår i eller görs tillgängligt genom våra tjänster – såsom text,
						grafik, logotyper, knappikoner, bilder, ljudklipp, digitala nedladdningar,
						datakompileringar och programvara – är Oneseeks eller dess innehållsleverantörers
						egendom och skyddas av internationell upphovsrätt, varumärkesrätt och andra immateriella
						rättigheter.
					</p>
					<p className="mt-4">
						Genom att skicka in, publicera eller visa innehåll i eller genom våra tjänster ger du
						oss en världsomspännande, icke-exklusiv, royaltyfri licens att använda, reproducera,
						ändra, anpassa, publicera, översätta, skapa derivatverk av, distribuera och visa sådant
						innehåll i alla medier i syfte att tillhandahålla och förbättra våra tjänster.
					</p>
				</section>

				<section className="mb-8">
					<h2 className="text-2xl font-semibold mb-4">6. Ändring och upphörande av våra tjänster</h2>
					<p>
						Vi förändrar och förbättrar ständigt våra tjänster. Vi kan lägga till eller ta bort
						funktioner, och vi kan tillfälligt eller permanent upphöra med en tjänst. Du kan sluta
						använda våra tjänster när som helst. Oneseek kan också sluta tillhandahålla tjänster till
						dig, eller införa nya begränsningar, när som helst.
					</p>
					<p className="mt-4">
						Vi anser att du äger din data och att det är viktigt att bevara din åtkomst till sådan
						data. Om vi avvecklar en tjänst kommer vi, där det är rimligt möjligt, att ge dig skälig
						förvarning och möjlighet att hämta ut information från den tjänsten.
					</p>
					<p className="mt-4">
						Vi förbehåller oss rätten att ändra dessa villkor när som helst. Om vi gör väsentliga
						ändringar kommer vi att informera dig via e-post eller genom att publicera en notis på
						vår webbplats innan ändringarna träder i kraft. Din fortsatta användning av våra tjänster
						efter ikraftträdandet innebär att du accepterar de ändrade villkoren.
					</p>
				</section>

				<section className="mb-8">
					<h2 className="text-2xl font-semibold mb-4">7. Garantier och ansvarsfriskrivningar</h2>
					<p>
						Vi tillhandahåller våra tjänster med en kommersiellt rimlig nivå av skicklighet och
						omsorg och hoppas att du ska ha nytta av dem. Men det finns vissa saker vi inte lovar
						om våra tjänster.
					</p>
					<p className="mt-4 uppercase font-bold">
						UTÖVER VAD SOM UTTRYCKLIGEN ANGES I DESSA VILLKOR ELLER TILLÄGGSVILLKOR GER VARKEN
						ONESEEK ELLER DESS LEVERANTÖRER ELLER DISTRIBUTÖRER NÅGRA SÄRSKILDA LÖFTEN OM
						TJÄNSTERNA. TILL EXEMPEL LÄMNAR VI INGA UTFÄSTELSER OM INNEHÅLLET I TJÄNSTERNA,
						TJÄNSTERNAS SPECIFIKA FUNKTIONER ELLER DERAS TILLFÖRLITLIGHET, TILLGÄNGLIGHET ELLER
						FÖRMÅGA ATT UPPFYLLA DINA BEHOV. TJÄNSTERNA TILLHANDAHÅLLS I BEFINTLIGT SKICK.
					</p>
					<p className="mt-4 uppercase font-bold">
						VISSA JURISDIKTIONER FÖRESKRIVER VISSA GARANTIER, SÅSOM UNDERFÖRSTÅDDA GARANTIER OM
						SÄLJBARHET, LÄMPLIGHET FÖR ETT SÄRSKILT ÄNDAMÅL OCH ICKE-INTRÅNG. I DEN UTSTRÄCKNING
						SOM LAGEN TILLÅTER UTESLUTER VI ALLA GARANTIER.
					</p>
				</section>

				<section className="mb-8">
					<h2 className="text-2xl font-semibold mb-4">8. Ansvar för våra tjänster</h2>
					<p className="uppercase font-bold">
						NÄR DET ÄR TILLÅTET ENLIGT LAG ÄR ONESEEK OCH DESS LEVERANTÖRER OCH DISTRIBUTÖRER INTE
						ANSVARIGA FÖR FÖRLORADE VINSTER, INTÄKTER ELLER DATA, EKONOMISKA FÖRLUSTER ELLER
						INDIREKTA, SÄRSKILDA, FÖLJDSKADOR, EXEMPLARISKA ELLER STRAFFSKADOR.
					</p>
					<p className="mt-4 uppercase font-bold">
						I DEN UTSTRÄCKNING SOM LAGEN TILLÅTER ÄR ONESEEKS OCH DESS LEVERANTÖRERS OCH
						DISTRIBUTÖRERS SAMLADE ANSVAR FÖR EVENTUELLA KRAV ENLIGT DESSA VILLKOR, INKLUSIVE FÖR
						UNDERFÖRSTÅDDA GARANTIER, BEGRÄNSAT TILL DET BELOPP DU BETALADE OSS FÖR ATT ANVÄNDA
						TJÄNSTERNA (ELLER, OM VI VÄLJER, ATT TILLHANDAHÅLLA TJÄNSTERNA IGEN).
					</p>
					<p className="mt-4 uppercase font-bold">
						I ALLA FALL ÄR ONESEEK OCH DESS LEVERANTÖRER OCH DISTRIBUTÖRER INTE ANSVARIGA FÖR NÅGON
						FÖRLUST ELLER SKADA SOM INTE SKÄLIGEN KAN FÖRUTSES.
					</p>
				</section>

				<section className="mb-8">
					<h2 className="text-2xl font-semibold mb-4">9. Skadeslöshet</h2>
					<p>
						You agree to defend, indemnify, and hold harmless SurfSense, its affiliates, and their
						respective officers, directors, employees, and agents from and against any claims,
						liabilities, damages, judgments, awards, losses, costs, expenses, or fees (including
						reasonable attorneys' fees) arising out of or relating to your violation of these Terms
						or your use of the Services, including, but not limited to, any use of the Services'
						content, services, and products other than as expressly authorized in these Terms.
					</p>
				</section>

				<section className="mb-8">
					<h2 className="text-2xl font-semibold mb-4">10. Dispute Resolution</h2>
					<p>
						Any dispute arising out of or relating to these Terms, including the validity,
						interpretation, breach, or termination thereof, shall be resolved by arbitration in
						accordance with the rules of the arbitration authority in the jurisdiction where
						SurfSense operates. The arbitration shall be conducted by one arbitrator, in the English
						language, and the decision of the arbitrator shall be final and binding on the parties.
					</p>
					<p className="mt-4">
						You agree that any dispute resolution proceedings will be conducted only on an
						individual basis and not in a class, consolidated, or representative action. If for any
						reason a claim proceeds in court rather than in arbitration, you waive any right to a
						jury trial.
					</p>
				</section>

				<section className="mb-8">
					<h2 className="text-2xl font-semibold mb-4">11. About these Terms</h2>
					<p>
						We may modify these terms or any additional terms that apply to a Service to, for
						example, reflect changes to the law or changes to our Services. You should look at the
						terms regularly. If you do not agree to the modified terms for a Service, you should
						discontinue your use of that Service.
					</p>
					<p className="mt-4">
						If there is a conflict between these terms and the additional terms, the additional
						terms will control for that conflict. These terms control the relationship between
						SurfSense and you. They do not create any third-party beneficiary rights.
					</p>
					<p className="mt-4">
						If you do not comply with these terms, and we don't take action right away, this doesn't
						mean that we are giving up any rights that we may have (such as taking action in the
						future). If it turns out that a particular term is not enforceable, this will not affect
						any other terms.
					</p>
				</section>

				<section className="mb-8">
					<h2 className="text-2xl font-semibold mb-4">12. Contact Us</h2>
					<p>If you have any questions about these Terms, please contact us at:</p>
					<p className="mt-2">
						<strong>Email:</strong> rohan@surfsense.com
					</p>
				</section>
			</div>
		</div>
	);
}
