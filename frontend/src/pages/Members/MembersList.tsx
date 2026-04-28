/**
 * Members list page with table, search, and filtering.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Box,
    Button,
    Card,
    CardContent,
    TextField,
    Typography,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    TablePagination,
    Chip,
    IconButton,
    InputAdornment,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogContentText,
    DialogActions,
    useMediaQuery,
    useTheme,
} from '@mui/material';
import {
    Add as AddIcon,
    Search as SearchIcon,
    Edit as EditIcon,
    Delete as DeleteIcon,
    FaceRetouchingNatural as EnrollIcon,
    CardMembership as CardMembershipIcon,
} from '@mui/icons-material';
import { membersApi, Member } from '@/api/members';
import { useLanguage } from '@/i18n/LanguageContext';
import { useAuth } from '@/contexts/AuthContext';

export const MembersList: React.FC = () => {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { t } = useLanguage();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin';
    const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

    const deleteMutation = useMutation({
        mutationFn: (id: string) => membersApi.deleteMember(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['members'] });
            setDeleteTarget(null);
        },
        onError: (error: any) => {
            alert(t.members.errorDeleting.replace('{error}', error?.response?.data?.detail || error?.message || 'Unknown'));
            setDeleteTarget(null);
        },
    });

    const [page, setPage] = useState(0);
    const [rowsPerPage, setRowsPerPage] = useState(25);
    const [search, setSearch] = useState('');

    const { data, isLoading } = useQuery({
        queryKey: ['members', page, rowsPerPage, search],
        queryFn: () =>
            membersApi.getMembers({
                skip: page * rowsPerPage,
                limit: rowsPerPage,
                search: search || undefined,
            }),
    });

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'active':
                return 'success';
            case 'inactive':
                return 'default';
            case 'suspended':
                return 'error';
            default:
                return 'default';
        }
    };

    return (
        <Box sx={{ px: { xs: 1, sm: 2, md: 3 } }}>
            <Box display="flex" flexDirection={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', sm: 'center' }} mb={3} gap={2}>
                <Typography variant={isMobile ? "h5" : "h4"}>{t.members.title}</Typography>
                <Button
                    variant="contained"
                    startIcon={<AddIcon />}
                    onClick={() => navigate('/members/new')}
                    fullWidth={isMobile}
                >
                    {t.members.addMember}
                </Button>
            </Box>

            <Card>
                <CardContent sx={{ p: { xs: 1.5, sm: 2, md: 3 } }}>
                    <TextField
                        fullWidth
                        placeholder={t.members.search}
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        InputProps={{
                            startAdornment: (
                                <InputAdornment position="start">
                                    <SearchIcon />
                                </InputAdornment>
                            ),
                        }}
                        sx={{ mb: 2 }}
                    />

                    <TableContainer sx={{ overflowX: 'auto' }}>
                        <Table size={isMobile ? "small" : "medium"}>
                            <TableHead>
                                <TableRow>
                                    <TableCell>{t.members.name}</TableCell>
                                    <TableCell>{t.members.idNumber}</TableCell>
                                    {!isMobile && <TableCell>{t.members.email}</TableCell>}
                                    <TableCell>{t.members.status}</TableCell>
                                    {!isMobile && <TableCell>'Membresía'</TableCell>}
                                    <TableCell align="right">{t.common.actions}</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {isLoading ? (
                                    <TableRow>
                                        <TableCell colSpan={isMobile ? 4 : 7} align="center">
                                            {t.members.loading}
                                        </TableCell>
                                    </TableRow>
                                ) : data?.members.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={isMobile ? 4 : 7} align="center">
                                            {t.members.noMembersFound}
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    data?.members.map((member: Member) => (
                                        <TableRow key={member.id} hover>
                                            <TableCell>
                                                {member.first_name} {member.last_name}
                                            </TableCell>
                                            <TableCell>{member.id_number || '—'}</TableCell>
                                            {!isMobile && <TableCell>{member.email}</TableCell>}
                                            <TableCell>
                                                <Chip
                                                    label={member.status}
                                                    color={getStatusColor(member.status)}
                                                    size="small"
                                                />
                                            </TableCell>
                                            {!isMobile && (
                                                <TableCell>
                                                    {member.membership_status === 'active' ? (
                                                        <Chip
                                                            label={`${member.membership_plan_name || 'Activa'} → ${member.membership_end_date || ''}`}
                                                            color="success"
                                                            size="small"
                                                        />
                                                    ) : member.membership_status === 'expired' ? (
                                                        <Chip
                                                            label={t.members.expired}
                                                            color="error"
                                                            size="small"
                                                        />
                                                    ) : (
                                                        <Chip
                                                            label={t.members.noMemberships}
                                                            color="default"
                                                            size="small"
                                                            variant="outlined"
                                                        />
                                                    )}
                                                </TableCell>
                                            )}
                                            <TableCell align="right">
                                                <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
                                                    <IconButton
                                                        size="small"
                                                        onClick={() => navigate(`/members/${member.id}/edit`)}
                                                        title={t.members.editMember}
                                                        color="primary"
                                                        sx={{ minWidth: 44, minHeight: 44 }}
                                                    >
                                                        <EditIcon />
                                                    </IconButton>
                                                    {!isMobile && (
                                                        <IconButton
                                                            size="small"
                                                            onClick={() => navigate(`/members/${member.id}/membership`)}
                                                            title={t.members.assignMembership}
                                                            color="secondary"
                                                            sx={{ minWidth: 44, minHeight: 44 }}
                                                        >
                                                            <CardMembershipIcon />
                                                        </IconButton>
                                                    )}
                                                    <IconButton
                                                        size="small"
                                                        onClick={() => navigate(`/members/${member.id}/enroll`)}
                                                        title={t.members.faceEnrollment}
                                                        color={member.facial_data_enrolled ? 'success' : 'warning'}
                                                        sx={{ minWidth: 44, minHeight: 44 }}
                                                    >
                                                        <EnrollIcon />
                                                    </IconButton>
                                                    {isAdmin && (
                                                        <IconButton size="small" title={t.members.delete} color="error" onClick={() => setDeleteTarget(member.id)} sx={{ minWidth: 44, minHeight: 44 }}>
                                                            <DeleteIcon />
                                                        </IconButton>
                                                    )}
                                                </Box>
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
            {/* Delete Confirmation Dialog */}
            <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)} fullWidth fullScreen={isMobile}>
                <DialogTitle>{t.members.deleteMember}</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        {t.members.deleteConfirmMsg}
                    </DialogContentText>
                </DialogContent>
                <DialogActions sx={{ p: { xs: 2, sm: 3 }, flexDirection: { xs: 'column', sm: 'row' }, gap: 1 }}>
                    <Button onClick={() => setDeleteTarget(null)} fullWidth={isMobile}>{t.members.cancel}</Button>
                    <Button
                        onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
                        color="error"
                        variant="contained"
                        disabled={deleteMutation.isPending}
                        fullWidth={isMobile}
                    >
                        {deleteMutation.isPending ? t.members.deleting : t.members.delete}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};
