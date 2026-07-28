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
    useMediaQuery,
    useTheme,
} from '@mui/material';
import { Add as AddIcon, Receipt as ReceiptIcon } from '@mui/icons-material';
import { salesApi, SalesCreate } from '@/api/sales';
import { useLanguage } from '@/i18n/LanguageContext';
import { useAppTimezone } from '@/hooks/useAppTimezone';
import { formatLocalDateTime } from '@/utils/dateTime';

const paymentMethods = ['cash', 'card', 'transfer'];

export const SalesList: React.FC = () => {
    const queryClient = useQueryClient();
    const { t } = useLanguage();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
    const timezone = useAppTimezone();
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
        <Box sx={{ px: { xs: 1, sm: 2, md: 3 } }}>
            <Box display="flex" flexDirection={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', sm: 'center' }} mb={3} gap={2}>
                <Typography variant={isMobile ? "h5" : "h4"}>{t.sales.title}</Typography>
                <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpenDialog(true)} fullWidth={isMobile}>
                    {t.sales.addTransaction}
                </Button>
            </Box>

            <Card>
                <CardContent sx={{ p: { xs: 1.5, sm: 2, md: 3 } }}>
                    <TableContainer sx={{ overflowX: 'auto' }}>
                        <Table size={isMobile ? "small" : "medium"}>
                            <TableHead>
                                <TableRow>
                                    <TableCell>{t.sales.invoice}</TableCell>
                                    <TableCell>{t.sales.member}</TableCell>
                                    {!isMobile && <TableCell>{t.sales.id}</TableCell>}
                                    <TableCell>{t.sales.amount}</TableCell>
                                    <TableCell>{t.sales.method}</TableCell>
                                    {!isMobile && <TableCell>{t.sales.date}</TableCell>}
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {isLoading ? (
                                    <TableRow>
                                        <TableCell colSpan={isMobile ? 4 : 6} align="center">{t.sales.loading}</TableCell>
                                    </TableRow>
                                ) : data?.transactions.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={isMobile ? 4 : 6} align="center">{t.sales.noTransactionsFound}</TableCell>
                                    </TableRow>
                                ) : (
                                    data?.transactions.map((tx) => (
                                        <TableRow key={tx.id} hover>
                                            <TableCell>
                                                <Box display="flex" alignItems="center" gap={1}>
                                                    <ReceiptIcon fontSize="small" color="action" />
                                                    <Typography variant="body2">{tx.invoice_number || '-'}</Typography>
                                                </Box>
                                            </TableCell>
                                            <TableCell>{tx.member_name || t.sales.unknown}</TableCell>
                                            {!isMobile && <TableCell>{tx.member_id_number || '-'}</TableCell>}
                                            <TableCell>${Number(tx.amount).toLocaleString()}</TableCell>
                                            <TableCell>
                                                <Chip
                                                    label={tx.payment_method.toUpperCase()}
                                                    color={getPaymentColor(tx.payment_method) as any}
                                                    size="small"
                                                />
                                            </TableCell>
                                            {!isMobile && (
                                                <TableCell>
                                                    {formatLocalDateTime(tx.transaction_date, timezone)}
                                                </TableCell>
                                            )}
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
            <Dialog open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="sm" fullWidth fullScreen={isMobile}>
                <DialogTitle>{t.sales.newTransactionTitle}</DialogTitle>
                <DialogContent>
                    <Box display="flex" flexDirection="column" gap={2} mt={1}>
                        <TextField
                            label={t.sales.memberId}
                            fullWidth
                            value={newTransaction.member_id}
                            onChange={(e) => setNewTransaction({ ...newTransaction, member_id: e.target.value })}
                            helperText={t.sales.memberIdHelper}
                        />
                        <TextField
                            label={t.sales.amount}
                            type="number"
                            fullWidth
                            value={newTransaction.amount}
                            onChange={(e) => setNewTransaction({ ...newTransaction, amount: Number(e.target.value) })}
                            InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
                        />
                        <FormControl fullWidth>
                            <InputLabel>{t.sales.paymentMethod}</InputLabel>
                            <Select
                                value={newTransaction.payment_method}
                                label={t.sales.paymentMethod}
                                onChange={(e) => setNewTransaction({ ...newTransaction, payment_method: e.target.value })}
                            >
                                {paymentMethods.map((m) => (
                                    <MenuItem key={m} value={m}>{m.toUpperCase()}</MenuItem>
                                ))}
                            </Select>
                        </FormControl>
                        <TextField
                            label={t.sales.notes}
                            fullWidth
                            multiline
                            rows={2}
                            value={newTransaction.notes}
                            onChange={(e) => setNewTransaction({ ...newTransaction, notes: e.target.value })}
                        />
                    </Box>
                </DialogContent>
                <DialogActions sx={{ p: { xs: 2, sm: 3 }, flexDirection: { xs: 'column', sm: 'row' }, gap: 1 }}>
                    <Button onClick={() => setOpenDialog(false)} fullWidth={isMobile}>{t.common.cancel}</Button>
                    <Button
                        onClick={() => createMutation.mutate(newTransaction)}
                        variant="contained"
                        disabled={!newTransaction.member_id || newTransaction.amount <= 0 || createMutation.isPending}
                        fullWidth={isMobile}
                    >
                        {createMutation.isPending ? t.sales.creating : t.sales.createTransaction}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};
