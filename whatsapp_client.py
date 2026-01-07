"""
WhatsApp Client using Green API.

Provides methods to send and receive WhatsApp messages.
"""
import requests
import time
from typing import Optional, Dict, Any


class GreenAPIWhatsAppClient:
    """Client for Green API WhatsApp integration."""

    def __init__(self, id_instance: str, api_token: str):
        """
        Initialize Green API client.

        Args:
            id_instance: Green API instance ID
            api_token: Green API token
        """
        self.id_instance = id_instance
        self.api_token = api_token
        self.base_url = f"https://7105.api.greenapi.com/waInstance{id_instance}"

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make HTTP request to Green API.

        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint
            data: Request payload

        Returns:
            Response JSON
        """
        url = f"{self.base_url}/{endpoint}/{self.api_token}"

        try:
            if method == "GET":
                response = requests.get(url, timeout=30)
            elif method == "POST":
                response = requests.post(url, json=data, timeout=30)
            elif method == "DELETE":
                response = requests.delete(url, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"Green API request error: {e}")
            return {}

    def send_typing(self, chat_id: str) -> bool:
        """
        Send typing indicator to WhatsApp chat.
        Shows "escribiendo..." status for ~10 seconds.

        Args:
            chat_id: WhatsApp chat ID (phone number with country code + @c.us)

        Returns:
            True if sent successfully
        """
        data = {
            "chatId": chat_id
        }

        response = self._make_request("POST", "sendChatStateComposing", data)
        return "result" in response or bool(response)

    def send_message(self, chat_id: str, message: str) -> bool:
        """
        Send text message to WhatsApp chat.

        Args:
            chat_id: WhatsApp chat ID (phone number with country code + @c.us)
            message: Message text to send

        Returns:
            True if sent successfully
        """
        data = {
            "chatId": chat_id,
            "message": message
        }

        response = self._make_request("POST", "sendMessage", data)
        return "idMessage" in response

    def receive_notification(self) -> Optional[Dict[str, Any]]:
        """
        Receive incoming notification (message, status, etc.).

        Uses HTTP API method - polls for new notifications.

        Returns:
            Notification data or None if no notifications
        """
        response = self._make_request("GET", "receiveNotification")

        if response and response.get("receiptId"):
            return response
        return None

    def delete_notification(self, receipt_id: str) -> bool:
        """
        Delete notification after processing.

        Args:
            receipt_id: Receipt ID from receiveNotification

        Returns:
            True if deleted successfully
        """
        # Note: deleteNotification endpoint requires apiToken BEFORE receiptId
        # URL format: /deleteNotification/{apiToken}/{receiptId}
        url = f"{self.base_url}/deleteNotification/{self.api_token}/{receipt_id}"

        try:
            response = requests.delete(url, timeout=30)
            response.raise_for_status()
            result = response.json()
            return result.get("result") == True
        except requests.exceptions.RequestException as e:
            print(f"Green API delete notification error: {e}")
            return False

    def get_state_instance(self) -> Dict[str, Any]:
        """
        Get instance state (authorized, blocked, etc.).

        Returns:
            State information
        """
        return self._make_request("GET", "getStateInstance")

    def process_incoming_message(self, notification: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Extract message data from notification.

        Args:
            notification: Notification from receiveNotification

        Returns:
            Dict with 'chat_id', 'sender', 'message', 'message_type', 'audio_url' or None
        """
        body = notification.get("body", {})
        type_webhook = body.get("typeWebhook")

        print(f"[WA-CLIENT] Processing notification:")
        print(f"[WA-CLIENT]   typeWebhook: {type_webhook}")

        # Only process incoming messages
        if type_webhook == "incomingMessageReceived":
            message_data = body.get("messageData", {})
            type_message = message_data.get("typeMessage")
            sender_data = body.get("senderData", {})

            print(f"[WA-CLIENT]   typeMessage: {type_message}")

            # Process text messages
            if type_message == "textMessage":
                text_data = message_data.get("textMessageData", {})
                print(f"[WA-CLIENT]   ✓ Text message detected")

                return {
                    "chat_id": sender_data.get("chatId", ""),
                    "sender": sender_data.get("sender", ""),
                    "sender_name": sender_data.get("senderName", "Unknown"),
                    "message": text_data.get("textMessage", ""),
                    "message_type": "text"
                }

            # Process audio messages
            elif type_message == "audioMessage":
                # Get download URL for audio file
                download_url = message_data.get("downloadUrl", "")

                print(f"[WA-CLIENT]   ✓ Audio message detected")
                print(f"[WA-CLIENT]   Download URL: {download_url[:100] if download_url else 'MISSING'}...")

                if not download_url:
                    print(f"[WA-CLIENT ERROR] Audio message has no downloadUrl!")
                    print(f"[WA-CLIENT] Full message_data: {message_data}")

                return {
                    "chat_id": sender_data.get("chatId", ""),
                    "sender": sender_data.get("sender", ""),
                    "sender_name": sender_data.get("senderName", "Unknown"),
                    "message": "[Audio message]",  # Placeholder, will be transcribed
                    "message_type": "audio",
                    "audio_url": download_url
                }
            else:
                print(f"[WA-CLIENT]   ⚠ Unsupported message type: {type_message}")

        else:
            print(f"[WA-CLIENT]   ⚠ Not an incoming message, skipping")

        return None


def format_message_for_whatsapp(message: str) -> str:
    """
    Format message text for WhatsApp (add formatting if needed).

    Args:
        message: Original message

    Returns:
        Formatted message
    """
    # WhatsApp supports markdown-like formatting:
    # *bold*, _italic_, ~strikethrough~, ```code```
    return message
