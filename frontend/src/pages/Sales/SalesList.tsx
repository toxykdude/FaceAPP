/**
 * Sales/Transactions list page.
 */
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Box,
    Typography,
    Button,
    Card,
    CardContent,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    TablePagination,
    Chip,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    TextField,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    InputAdornment,
} from '@mui/material';
import { Add as AddIcon, Receipt as ReceiptIcon } from '@mui/icons-material';
import { salesApi, SalesCreate } from '@/api/sales';

const paymentMethods = ['cash', 'card', 'transfer'];

export const SalesList: React.FC = () => {
    const queryClient = useQueryClient();
    const [page, setPage] = useState(0);
    const [rowsPerPage, setRowsPerPage] = useState(25);
    const [openDialog, setOpenDialog] = useState(false);

    const [newTransaction, setNewTransaction] = useState<SalesCreate>({
        member_id: '',
        amount: 0,
        payment_method: 'cash',
        notes: '',
    });

    const { data, isLoading } = useQuery({
        queryKey: ['sales', page, rowsPerPage],
        queryFn: () => salesApi.getTransactions({ skip: page * rowsPerPage, limit: rowsPerPage }),
    });

    const createMutation = useMutation({
        mutationFn: (data: SalesCreate) => salesApi.createTransaction(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sales'] });
            setOpenDialog(false);
            setNewTransaction({ member_id: '', amount: 0, payment_method: 'cash', notes: '' });
        },
    });

    const getPaymentColor = (method: string) => {
        switch (method) {
            case 'cash': return 'success';
            case 'card': return 'primary';
            case 'transfer': return 'warning';
            default: return 'default';
        }
    };

    return (
        <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                <Typography variant="h4">Sales</Typography>
                <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpenDialog(true)}>
                    New Transaction
                </Button>
            </Box>

            <Card>
                <CardContent>
                    <TableContainer>
                        <Table>
                            <TableHead>
                                <TableRow>
                                    <TableCell>Invoice</TableCell>
                                    <TableCell>Member</TableCell>
                                    <TableCell>Amount</TableCell>
                                    <TableCell>Method</TableCell>
                                    <TableCell>Date</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {isLoading ? (
                                    <TableRow>
                                        <TableCell colSpan={5} align="center">Loading...</TableCell>
                                    </TableRow>
                                ) : data?.transactions.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={5} align="center">No transactions found</TableCell>
                                    </TableRow>
                                ) : (
                                    data?.transactions.map((tx) => (
                                        <TableRow key={tx.id} hover>
                                            <TableCell>
                                                <Box display="flex" alignItems="center" gap={1}>
                                                    <ReceiptIcon fontSize="small" color="action" />
                                                    <Typography variant="body2">{tx.invoice_number}</Typography>
                                                </Box>
                                            </TableCell>
                                            <TableCell>{tx.member_id.substring(0, 8)}...</TableCell>
                                            <TableCell>${tx.amount.toFixed(2)}</TableCell>
                                            <TableCell>
                                                <Chip
                                                    label={tx.payment_method.toUpperCase()}
                                                    color={getPaymentColor(tx.payment_method) as any}
                                                    size="small"
                                                />
                                            </TableCell>
                                            <TableCell>
                                                {new Date(tx.transaction_date).toLocaleDateString()}
                                            </TableCell>
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table>
                    </TableContainer>

                    <TablePagination
                        component="div"
                        count={data?.total || 0}
                        page={page}
                        onPageChange={(_, newPage) => setPage(newPage)}
                        rowsPerPage={rowsPerPage}
                        onRowsPerPageChange={(e) => {
                            setRowsPerPage(parseInt(e.target.value, 10));
                            setPage(0);
                        }}
                    />
                </CardContent>
            </Card>

            {/* Create Transaction Dialog */}
            <Dialog open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="sm" fullWidth>
                <DialogTitle>New Transaction</DialogTitle>
                <DialogContent>
                    <Box display="flex" flexDirection="column" gap={2} mt={1}>
                        <TextField
                            label="Member ID"
                            fullWidth
                            value={newTransaction.member_id}
                            onChange={(e) => setNewTransaction({ ...newTransaction, member_id: e.target.value })}
                            helperText="Enter the member UUID"
                        />
                        <TextField
                            label="Amount"
                            type="number"
                            fullWidth
                            value={newTransaction.amount}
                            onChange={(e) => setNewTransaction({ ...newTransaction, amount: Number(e.target.value) })}
                            InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
                        />
                        <FormControl fullWidth>
                            <InputLabel>Payment Method</InputLabel>
                            <Select
                                value={newTransaction.payment_method}
                                label="Payment Method"
                                onChange={(e) => setNewTransaction({ ...newTransaction, payment_method: e.target.value })}
                            >
                                {paymentMethods.map((m) => (
                                    <MenuItem key={m} value={m}>{m.toUpperCase()}</MenuItem>
                                ))}
                            </Select>
                        </FormControl>
                        <TextField
                            label="Notes"
                            fullWidth
                            multiline
                            rows={2}
                            value={newTransaction.notes}
                            onChange={(e) => setNewTransaction({ ...newTransaction, notes: e.target.value })}
                        />
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpenDialog(false)}>Cancel</Button>
                    <Button
                        onClick={() => createMutation.mutate(newTransaction)}
                        variant="contained"
                        disabled={!newTransaction.member_id || newTransaction.amount <= 0 || createMutation.isPending}
                    >
                        {createMutation.isPending ? 'Creating...' : 'Create Transaction'}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};
