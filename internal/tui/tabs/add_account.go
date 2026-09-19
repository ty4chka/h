package tabs

type AddAccountState struct {
	Step      int // 0: method select, 1: name, 2: phone, 3: code
	Method    int // 0: classic, 1: qr
	Name      string
	Phone     string
	Code      string
	Password  string
}

func NewAddAccountState() AddAccountState {
	return AddAccountState{Step: 0, Method: 0}
}
