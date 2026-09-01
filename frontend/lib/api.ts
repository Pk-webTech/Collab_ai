import { supabase } from "./supabase";

const API_URL = process.env.NEXT_PUBLIC_API_URL!;

async function authHeaders() {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new Error("Not signed in");
  return { Authorization: `Bearer ${token}` };
}

export type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export async function listConversations(): Promise<Conversation[]> {
  const res = await fetch(`${API_URL}/api/conversations`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to load conversations");
  return res.json();
}

export async function createConversation(title?: string): Promise<Conversation> {
  const res = await fetch(`${API_URL}/api/conversations`, {
    method: "POST",
    headers: { ...(await authHeaders()), "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error("Failed to create conversation");
  return res.json();
}

export async function getMessages(conversationId: string): Promise<Message[]> {
  const res = await fetch(`${API_URL}/api/conversations/${conversationId}/messages`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to load messages");
  return res.json();
}

export type Room = {
  id: string;
  name: string;
  owner_id: string;
  join_code: string;
  created_at: string;
};

export type RoomMember = {
  user_id: string;
  display_name: string | null;
  joined_at: string;
};

export type RoomMessage = {
  id: string;
  sender_type: "user" | "ai";
  user_id: string | null;
  display_name: string | null;
  content: string;
  created_at: string;
};

export async function listRooms(): Promise<Room[]> {
  const res = await fetch(`${API_URL}/api/rooms`, { headers: await authHeaders() });
  if (!res.ok) throw new Error("Failed to load rooms");
  return res.json();
}

export async function createRoom(name: string): Promise<Room> {
  const res = await fetch(`${API_URL}/api/rooms`, {
    method: "POST",
    headers: { ...(await authHeaders()), "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error("Failed to create room");
  return res.json();
}

export async function joinRoom(joinCode: string): Promise<Room> {
  const res = await fetch(`${API_URL}/api/rooms/join`, {
    method: "POST",
    headers: { ...(await authHeaders()), "Content-Type": "application/json" },
    body: JSON.stringify({ join_code: joinCode }),
  });
  if (!res.ok) throw new Error("Failed to join room — check the code");
  return res.json();
}

export async function getRoomMembers(roomId: string): Promise<RoomMember[]> {
  const res = await fetch(`${API_URL}/api/rooms/${roomId}/members`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to load members");
  return res.json();
}

export async function getRoomMessages(roomId: string): Promise<RoomMessage[]> {
  const res = await fetch(`${API_URL}/api/rooms/${roomId}/messages`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to load room messages");
  return res.json();
}

export async function sendRoomMessage(roomId: string, content: string): Promise<RoomMessage> {
  const res = await fetch(`${API_URL}/api/rooms/${roomId}/messages`, {
    method: "POST",
    headers: { ...(await authHeaders()), "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error("Failed to send message");
  return res.json();
}

/** Streams the assistant's reply, calling onChunk as text arrives. */
export async function sendMessageStream(
  conversationId: string,
  message: string,
  onChunk: (text: string) => void
): Promise<void> {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { ...(await authHeaders()), "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId, message }),
  });
  if (!res.ok || !res.body) throw new Error("Failed to send message");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}
