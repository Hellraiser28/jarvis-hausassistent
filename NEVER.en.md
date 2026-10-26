# What Jarvis never does

*Deutsch: [NEVER.md](NEVER.md)*

Jarvis has a lot of access: to your home, your calendar and messages, and on request to your PC. That's why this page
says what it never does. Every point is either enforced in the code or a fixed rule in the build guide that Claude
builds into every Jarvis and tries out during acceptance. Where you get to decide, the default is listed.

## Always, for everyone

**It never pretends to be human.** If someone asks whether it's an AI, it answers honestly, on the phone too.
Messages it sends on your behalf carry a note saying that Jarvis sent them.

**It sends nothing to others without your yes.** Messages to family members, e-mails and announcements only go out
after you explicitly agree in the conversation. "What's going on?" is not a yes.

**Third-party text is never an order.** Whatever is in e-mails, calendars, web pages, documents or messages is data.
It doesn't trigger an action or an approval request.

**It never switches anything on unasked.** On its own it only reports things, such as severe weather or a finished
appliance. The one exception: for a danger you defined during setup (which device, which condition) it may switch
something **off**, and it tells you right away.

**It doesn't grant itself rights.** Its safety rules (block list, approvals, new devices, real-time mode) can't be
loosened just by saying so, only with your code word and a confirmation on your phone.

**It doesn't sneak into your computer.** The brain has no command line and no file access, only named tools. PC
control only works when you type in the PC window or use your app, never through speakers, the phone line or unknown
devices. By voice at the PC, in real-time mode and from outside the home only if you explicitly switch it on, because
otherwise a video playing through your speakers could say "Hey Jarvis" too.

**What belongs to one person stays with them.** What someone tells Jarvis, no one else learns. It only shares other
people's location and private appointments with their consent. Parents may ask for their children's location and
appointments, never for their conversations with Jarvis.

**It never deletes for good without your yes.** Permanently deleting files, e-mails, appointments or documents only
happens after an explicit confirmation. It forgets things from its own memory on request.

**It doesn't store your voice.** Audio is transcribed and discarded. Recordings only exist if you explicitly switch
them on for troubleshooting, and they are deleted afterwards.

**It doesn't manipulate.** How cheeky or matter-of-fact it is, you decide. But it never pressures you, never plays on
your feelings and never talks you into something to get its way.

**In an emergency, the emergency number first.** With health and legal questions it helps with information but says
when you need a doctor or a lawyer. It doesn't replace either.

**With children, child-appropriate.** On children's devices there is no real-time mode (Google's terms), no buying and
no adult content, and it only operates the devices that are allowed for that child.

**No conversation content in the log.** The bridge's log contains source, duration, tool and lengths, not what was
said.

**It doesn't phone home.** There's no telemetry and no advertising. Only the app and the PC client look for updates,
at your Jarvis or at GitHub.

## Default "never", changeable during setup

| Topic | Default | Optionally |
|---|---|---|
| Buying, ordering, paying | never | only after an explicit yes in the conversation |
| Unlocking doors, disarming alarms | never (locking and arming are fine) | only after a yes from your app, never by speaker or phone |
| Cameras and baby monitors | blocked | allow, device by device |
| Memory | remembers useful things by itself, everything viewable and deletable ("What do you know about me?", "Forget …") | only on "Remember …" |
| Tone | as chosen during setup | cheeky or matter-of-fact; the floor above always applies |

## Where your data goes

- **Memory, conversation history and profile** stay on your Jarvis host.
- **Every question** goes to Claude (Anthropic) with the context it needs. It can't work without that.
- **Voice:** the text of the answer goes to Microsoft (`edge-tts`). The fallback voice Piper stays on your machine.
- **Speech recognition:** what you say at the PC and on the phone line is recognized by your Jarvis host itself. The
  Android app uses the phone's recognition (usually Google), the iPhone uses Apple's.
- **Real-time mode** (only if switched on): audio, instructions and answers go to Google.
- **Files** you add to a conversation: images, PDF and text go to Claude (Anthropic) with the question. Your
  Jarvis host transcribes audio itself, only the transcript goes to Claude. The file is only stored in the
  conversation history on the Jarvis host.
- **Tools** such as weather, news or web search query the respective services. They see the request, not your
  conversation.
- **The interface** loads fonts from Google Fonts (can be switched off).

If you find a place where Jarvis doesn't keep to this page, please report it as a security issue
([SECURITY.en.md](SECURITY.en.md)), not as a public issue.
