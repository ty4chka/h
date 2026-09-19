package telegram

import (
	"context"
	"fmt"
)

type Client struct {
	APIID   int
	APIHash string
	Phone   string
	Session string
	Connected bool
}

func NewClient(apiID int, apiHash string) *Client {
	return &Client{APIID: apiID, APIHash: apiHash}
}

func (c *Client) Connect(ctx context.Context, phone string) error {
	c.Phone = phone
	c.Connected = true
	fmt.Printf("[Telegram] Connected as %s\n", phone)
	return nil
}

func (c *Client) ConnectQR(ctx context.Context) error {
	c.Connected = true
	fmt.Println("[Telegram] Connected via QR")
	return nil
}

func (c *Client) Disconnect() error {
	c.Connected = false
	return nil
}
