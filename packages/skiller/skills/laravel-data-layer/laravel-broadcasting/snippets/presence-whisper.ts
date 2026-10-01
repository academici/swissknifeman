// Source: anonymized production Laravel project

// Presence-channel: list «who is online» + whisper (client-client without server).
// Server authorization presence-channel MUST return an array of data
// user (see channels.php), otherwise here/joining will not work.

interface Member {
    id: number;
    name: string;
}

const channel = window.Echo.join(`warehouse.${warehouseId}`)
    // Full list of participants when connecting.
    .here((members: Member[]) => {
        console.log('online:', members.map((m) => m.name));
    })
    // Someone has joined.
    .joining((member: Member) => {
        console.log('joined:', member.name);
    })
    // Someone came out.
    .leaving((member: Member) => {
        console.log('left:', member.name);
    })
    .error((error: unknown) => {
        console.error('presence auth failed', error);
    });

// --- Whisper: ephemeral events between clients ---
// Only works on private/presence channels, does not pass through Laravel —
// ideal for typing-indicators and cursor positions.

// Dispatch (for example, by input-event, with debounce):
channel.whisper('typing', {
    userId: currentUserId,
    name: currentUserName,
});

// Reception with other participants:
channel.listenForWhisper('typing', (e: { userId: number; name: string }) => {
    showTypingIndicator(e.name);
});

// Leave channel (for example, when unmount component):
// window.Echo.leave(`warehouse.${warehouseId}`);
